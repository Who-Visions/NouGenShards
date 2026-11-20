package main

import (
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math"
	"net/http"
	"regexp"
	"strings"
	"time"

	"github.com/gorilla/websocket"
)

// Config holds the relay's limits and routing. Zero values mean the defaults.
type Config struct {
	HostSuffix  string        // e.g. ".relay.example": <id>.relay.example routes to <id>
	Timeout     time.Duration // per public request, then 504
	MaxBody     int64         // request and response body cap, bytes
	IdleTimeout time.Duration // drop a node that has sent nothing (not even a ping) for this long
}

func (c Config) withDefaults() Config {
	if c.Timeout <= 0 {
		c.Timeout = defaultTimeout
	}
	if c.MaxBody <= 0 {
		c.MaxBody = defaultMaxBody
	}
	if c.IdleTimeout <= 0 {
		c.IdleTimeout = 90 * time.Second // three missed 20 s heartbeats plus slack
	}
	return c
}

// Server is the relay: node sockets in, public requests through.
type Server struct {
	cfg   Config
	store AuthStore
	hub   *Hub
	up    websocket.Upgrader
}

func NewServer(cfg Config, st AuthStore) *Server {
	return &Server{
		cfg: cfg.withDefaults(), store: st, hub: NewHub(),
		// Nodes are not browsers, so there is no Origin to check; the bearer token is the gate.
		up: websocket.Upgrader{CheckOrigin: func(*http.Request) bool { return true }},
	}
}

func jsonOut(w http.ResponseWriter, status int, v any) {
	w.Header().Set("content-type", "application/json")
	w.Header().Set("cache-control", "no-store")
	w.WriteHeader(status)
	_, _ = io.WriteString(w, mustJSON(v))
}

func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch r.URL.Path {
	case "/_relay/health":
		_, _ = io.WriteString(w, "ok")
		return
	case "/_relay/connect", "/_relay/status":
		id := strings.ToLower(r.URL.Query().Get("id"))
		if !validID(id) {
			jsonOut(w, http.StatusBadRequest, map[string]string{"error": "bad id"})
			return
		}
		// Status needs the node's own token too: open status would let anyone enumerate
		// ids and learn which nodes are online.
		ok, err := s.authorized(id, r)
		if err != nil {
			log.Printf("auth store error: %v", err)
			jsonOut(w, http.StatusServiceUnavailable, map[string]string{"error": "auth store unavailable"})
			return
		}
		if !ok {
			jsonOut(w, http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
			return
		}
		if r.URL.Path == "/_relay/status" {
			s.status(w, id)
			return
		}
		s.connect(w, r, id)
		return
	}
	id, path, ok := route(r.Host, r.URL, s.cfg.HostSuffix)
	if !ok {
		http.Error(w, "Not found", http.StatusNotFound)
		return
	}
	s.forward(w, r, id, path)
}

// authorized checks the bearer token against the stored sha256. The hash is always
// computed, found or not, so a missing id does not answer faster than a wrong token.
func (s *Server) authorized(id string, r *http.Request) (bool, error) {
	tok := bearer(r.Header)
	if tok == "" {
		return false, nil
	}
	want, found, err := s.store.Hash(id)
	if err != nil {
		return false, err
	}
	got := sha256Hex(tok)
	return found && hashesEqual(got, want), nil
}

func (s *Server) status(w http.ResponseWriter, id string) {
	sess := s.hub.get(id)
	var since any
	if sess != nil {
		since = sess.since
	}
	jsonOut(w, http.StatusOK, map[string]any{"live": sess != nil, "transport": "relay", "since": since})
}

func (s *Server) connect(w http.ResponseWriter, r *http.Request, id string) {
	if !websocket.IsWebSocketUpgrade(r) {
		http.Error(w, "expected websocket", http.StatusUpgradeRequired)
		return
	}
	conn, err := s.up.Upgrade(w, r, nil) // on error the upgrader has already replied
	if err != nil {
		return
	}
	// Room for a base64 body plus headers; anything bigger is a protocol abuse.
	conn.SetReadLimit((s.cfg.MaxBody/3+1)*4 + 256<<10)
	sess := newSession(id, conn)
	if old := s.hub.register(sess); old != nil {
		old.failAll()
		_ = old.conn.WriteControl(websocket.CloseMessage,
			websocket.FormatCloseMessage(CloseReplaced, "replaced"), time.Now().Add(time.Second))
		_ = old.conn.Close()
	}
	_ = sess.writeJSON(readyFrame{T: "ready", V: Protocol, Since: sess.since})
	s.readLoop(sess)
}

func (s *Server) readLoop(sess *session) {
	defer func() {
		if s.hub.remove(sess) {
			sess.failAll()
		}
		_ = sess.conn.Close()
	}()
	for {
		_ = sess.conn.SetReadDeadline(time.Now().Add(s.cfg.IdleTimeout))
		_, msg, err := sess.conn.ReadMessage()
		if err != nil {
			return
		}
		var head struct {
			T string `json:"t"`
		}
		if json.Unmarshal(msg, &head) != nil {
			continue // not JSON: ignore, as the Worker does
		}
		switch head.T {
		case "ping":
			if sess.writeText(`{"t":"pong"}`) != nil {
				return
			}
		case "res":
			var f resFrame
			if json.Unmarshal(msg, &f) == nil {
				sess.deliver(&f)
			}
		}
	}
}

const offlinePage = `<!doctype html><meta charset="utf-8"><title>Node offline</title><body style="font-family:system-ui;background:#0d0d0d;color:#f2eee6;display:grid;place-items:center;min-height:100vh;margin:0"><div style="max-width:32rem;padding:1rem"><h1>This node is offline</h1><p>%s is not connected right now. If this is your computer, make sure it is on and NouGen is running.</p></div>`

func offline(w http.ResponseWriter, id string) {
	w.Header().Set("content-type", "text/html; charset=utf-8")
	w.Header().Set("cache-control", "no-store")
	w.WriteHeader(http.StatusBadGateway)
	_, _ = fmt.Fprintf(w, offlinePage, id) // id already matched validID, so it is HTML-safe
}

// readCapped reads a request body without buffering more than max bytes. ok=false when too large.
func readCapped(r *http.Request, max int64) ([]byte, bool) {
	if r.Body == nil || r.Body == http.NoBody {
		return nil, true
	}
	if r.ContentLength > max {
		return nil, false
	}
	b, err := io.ReadAll(io.LimitReader(r.Body, max+1))
	if err != nil || int64(len(b)) > max {
		return nil, false
	}
	return b, true
}

func (s *Server) forward(w http.ResponseWriter, r *http.Request, id, path string) {
	sess := s.hub.get(id)
	if sess == nil {
		offline(w, id)
		return
	}
	body, ok := readCapped(r, s.cfg.MaxBody)
	if !ok {
		http.Error(w, "request too large for relay", http.StatusRequestEntityTooLarge)
		return
	}
	headers := map[string]string{}
	for k, vs := range r.Header {
		if !hop[strings.ToLower(k)] {
			headers[k] = strings.Join(vs, ", ")
		}
	}
	rid := newRid()
	ch := sess.addPending(rid)
	if ch == nil {
		http.Error(w, "node did not answer in time", http.StatusGatewayTimeout)
		return
	}
	err := sess.writeJSON(reqFrame{T: "req", Rid: rid, Method: r.Method, Path: path, Headers: headers,
		Body: base64.StdEncoding.EncodeToString(body)})
	if err != nil {
		sess.dropPending(rid)
		http.Error(w, "node did not answer in time", http.StatusGatewayTimeout)
		return
	}
	timer := time.NewTimer(s.cfg.Timeout)
	defer timer.Stop()
	var res *resFrame
	select {
	case res = <-ch:
	case <-timer.C:
		sess.dropPending(rid)
	case <-r.Context().Done():
		sess.dropPending(rid)
		return
	}
	if res == nil {
		http.Error(w, "node did not answer in time", http.StatusGatewayTimeout)
		return
	}
	s.relayResponse(w, r, res)
}

var headerNameRE = regexp.MustCompile("^[!#$%&'*+\\-.^_`|~0-9A-Za-z]+$")

func validHeader(k, v string) bool {
	return headerNameRE.MatchString(k) && !strings.ContainsAny(v, "\r\n\x00")
}

// relayResponse checks everything the node sent before passing it on: the node is
// outside the trust boundary.
func (s *Server) relayResponse(w http.ResponseWriter, r *http.Request, res *resFrame) {
	bad := func(msg string) { http.Error(w, msg, http.StatusBadGateway) }

	var st float64
	if json.Unmarshal(res.Status, &st) != nil || st != math.Trunc(st) || st < 200 || st > 599 {
		bad("node sent an invalid status")
		return
	}
	status := int(st)

	var encoded string
	if len(res.Body) > 0 && string(res.Body) != "null" {
		if json.Unmarshal(res.Body, &encoded) != nil {
			bad("node sent an invalid body")
			return
		}
	}
	if int64(len(encoded)) > (s.cfg.MaxBody+2)/3*4 {
		bad("node response too large for relay")
		return
	}

	pairs, ok := parseHeaders(res.Headers)
	if !ok {
		bad("node sent invalid headers")
		return
	}
	h := http.Header{}
	for _, p := range pairs {
		if !validHeader(p[0], p[1]) {
			bad("node sent invalid headers")
			return
		}
		if hop[strings.ToLower(p[0])] {
			continue
		}
		h.Add(p[0], p[1])
	}
	h.Set("x-nougen-transport", "relay")

	nullBody := status == 204 || status == 304 || r.Method == http.MethodHead
	var out []byte
	if !nullBody {
		var err error
		out, err = base64.StdEncoding.DecodeString(encoded)
		if err != nil {
			bad("node sent an invalid body")
			return
		}
		// The encoded-length check above is a cheap pre-filter; this is the exact decoded limit.
		if int64(len(out)) > s.cfg.MaxBody {
			bad("node response too large for relay")
			return
		}
	}
	for k, vs := range h {
		for _, v := range vs {
			w.Header().Add(k, v)
		}
	}
	w.WriteHeader(status)
	if !nullBody {
		_, _ = w.Write(out)
	}
}

// parseHeaders accepts what the Worker accepts: null/absent, a list of [name, value]
// pairs (repeated headers such as Set-Cookie survive), or a plain object.
func parseHeaders(raw []byte) ([][2]string, bool) {
	s := strings.TrimSpace(string(raw))
	if s == "" || s == "null" {
		return nil, true
	}
	switch s[0] {
	case '[':
		var list []any
		if json.Unmarshal(raw, &list) != nil {
			return nil, false
		}
		out := make([][2]string, 0, len(list))
		for _, it := range list {
			pair, ok := it.([]any)
			if !ok || len(pair) != 2 {
				return nil, false
			}
			k, ok1 := pair[0].(string)
			v, ok2 := pair[1].(string)
			if !ok1 || !ok2 {
				return nil, false
			}
			out = append(out, [2]string{k, v})
		}
		return out, true
	case '{':
		var obj map[string]any
		if json.Unmarshal(raw, &obj) != nil {
			return nil, false
		}
		out := make([][2]string, 0, len(obj))
		for k, v := range obj {
			sv, ok := v.(string)
			if !ok {
				return nil, false
			}
			out = append(out, [2]string{k, sv})
		}
		return out, true
	}
	return nil, false
}
