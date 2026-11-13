// ngsnode is the resident front process of a NouGenShards node.
//
// It owns the node's listening socket. Routes that have been ported are
// served here, natively; every other route is reverse-proxied to the Python
// app (app.py), which this process starts and supervises as a worker on a
// loopback port. Porting a route means adding a handler here: the proxy
// fallback stops seeing it and the Python handler becomes dead code.
//
// Native today:
//
//	GET  /livez             liveness of this process and its worker (open)
//	GET  /v1/vector/status  mapped matrices (token)
//	POST /v1/vector/search  exact cosine top-N over the vault's matrices (token)
//
// Usage:
//
//	ngsnode [-listen host:port] [-vault dir] [-worker-port n] -- worker-cmd [args...]
//
// The worker is started with NGS_PORT set to the worker port and NGS_HOST set
// to 127.0.0.1. Without a worker command only the native routes are served.
package main

import (
	"context"
	"crypto/subtle"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"log"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"strings"
	"sync"
	"sync/atomic"
	"syscall"
	"time"
)

const maxSearchBody = 1 << 20 // a 768-d embedding as JSON is ~15 KB

type node struct {
	token  string
	index  *vectorIndex
	proxy  *httputil.ReverseProxy // nil without a worker
	worker *worker
	start  time.Time
}

func envOr(key, fallback string) string {
	if v := strings.TrimSpace(os.Getenv(key)); v != "" {
		return v
	}
	return fallback
}

// requestToken reads the node token the same three ways the Python app does:
// X-NGS-Token, Authorization: Bearer, or ?token=.
func requestToken(r *http.Request) string {
	if t := r.Header.Get("X-NGS-Token"); t != "" {
		return t
	}
	if a := r.Header.Get("Authorization"); len(a) > 7 && strings.EqualFold(a[:7], "Bearer ") {
		return strings.TrimSpace(a[7:])
	}
	return r.URL.Query().Get("token")
}

// authed reports whether the request carries the node token. With no token
// configured every data route is refused (503), as in the Python app.
func (n *node) authed(w http.ResponseWriter, r *http.Request) bool {
	if n.token == "" {
		writeJSON(w, http.StatusServiceUnavailable, map[string]string{"detail": "node token is not configured"})
		return false
	}
	if subtle.ConstantTimeCompare([]byte(requestToken(r)), []byte(n.token)) != 1 {
		writeJSON(w, http.StatusUnauthorized, map[string]string{"detail": "Invalid or missing node token."})
		return false
	}
	return true
}

func writeJSON(w http.ResponseWriter, code int, v interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(code)
	_ = json.NewEncoder(w).Encode(v)
}

func (n *node) handleLivez(w http.ResponseWriter, r *http.Request) {
	out := map[string]interface{}{
		"status":   "ok",
		"front":    "go",
		"uptime_s": int(time.Since(n.start).Seconds()),
	}
	if n.worker != nil {
		out["worker"] = n.worker.state()
	}
	writeJSON(w, http.StatusOK, out)
}

func (n *node) handleVectorStatus(w http.ResponseWriter, r *http.Request) {
	if !n.authed(w, r) {
		return
	}
	errs := n.index.refresh()
	msgs := make([]string, 0, len(errs))
	for _, e := range errs {
		msgs = append(msgs, e.Error())
	}
	writeJSON(w, http.StatusOK, map[string]interface{}{"dbs": n.index.status(), "errors": msgs})
}

type searchRequest struct {
	Embedding []float32 `json:"embedding"`
	TopN      int       `json:"top_n"`
	DomainKey string    `json:"domain_key"`
}

func (n *node) handleVectorSearch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"detail": "POST only"})
		return
	}
	if !n.authed(w, r) {
		return
	}
	var req searchRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxSearchBody)).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"detail": "bad JSON body: " + err.Error()})
		return
	}
	if len(req.Embedding) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"detail": "embedding is required"})
		return
	}
	if req.TopN <= 0 {
		req.TopN = 200
	}
	if req.TopN > 5000 {
		req.TopN = 5000
	}
	for _, e := range n.index.refresh() {
		log.Printf("vector index: %v", e)
	}
	started := time.Now()
	res := n.index.search(req.Embedding, req.TopN, req.DomainKey)
	writeJSON(w, http.StatusOK, map[string]interface{}{
		"hits": res.Hits, "rows": res.Rows, "dbs": res.DBs,
		"skipped_dim_mismatch": res.Skipped,
		"ms":                   float64(time.Since(started).Microseconds()) / 1000,
	})
}

func (n *node) handleFallback(w http.ResponseWriter, r *http.Request) {
	if n.proxy == nil {
		writeJSON(w, http.StatusNotFound, map[string]string{"detail": "Not Found"})
		return
	}
	n.proxy.ServeHTTP(w, r)
}

func (n *node) routes() http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/livez", n.handleLivez)
	mux.HandleFunc("/v1/vector/status", n.handleVectorStatus)
	mux.HandleFunc("/v1/vector/search", n.handleVectorSearch)
	mux.HandleFunc("/", n.handleFallback)
	return mux
}

func newProxy(target *url.URL) *httputil.ReverseProxy {
	p := httputil.NewSingleHostReverseProxy(target)
	p.FlushInterval = -1 // /mcp streams (SSE); never buffer a response
	p.Transport = &http.Transport{
		DialContext:           (&net.Dialer{Timeout: 5 * time.Second, KeepAlive: 30 * time.Second}).DialContext,
		MaxIdleConns:          64,
		MaxIdleConnsPerHost:   64,
		IdleConnTimeout:       90 * time.Second,
		ResponseHeaderTimeout: 0, // slow recalls and long-lived streams are the worker's call
	}
	director := p.Director
	p.Director = func(r *http.Request) {
		host := r.Host
		director(r)
		r.Host = host // the app builds absolute URLs (OAuth, MCP) from Host
	}
	p.ErrorHandler = func(w http.ResponseWriter, r *http.Request, err error) {
		if errors.Is(err, context.Canceled) {
			return // the client went away
		}
		log.Printf("proxy %s %s: %v", r.Method, r.URL.Path, err)
		w.Header().Set("Retry-After", "2")
		writeJSON(w, http.StatusBadGateway, map[string]string{"detail": "node worker is not answering", "front": "go"})
	}
	return p
}

// worker supervises the Python app: start, restart with backoff, stop.
type worker struct {
	argv     []string
	port     int
	mu       sync.Mutex
	cmd      *exec.Cmd
	restarts int
	lastExit string
	stopping atomic.Bool
	done     chan struct{}
}

func (w *worker) state() map[string]interface{} {
	w.mu.Lock()
	defer w.mu.Unlock()
	st := map[string]interface{}{"port": w.port, "restarts": w.restarts, "running": w.cmd != nil}
	if w.cmd != nil && w.cmd.Process != nil {
		st["pid"] = w.cmd.Process.Pid
	}
	if w.lastExit != "" {
		st["last_exit"] = w.lastExit
	}
	return st
}

func (w *worker) run() {
	defer close(w.done)
	backoff := time.Second
	for !w.stopping.Load() {
		cmd := exec.Command(w.argv[0], w.argv[1:]...)
		cmd.Stdout, cmd.Stderr = os.Stdout, os.Stderr
		cmd.Env = append(os.Environ(),
			fmt.Sprintf("NGS_PORT=%d", w.port), "NGS_HOST=127.0.0.1", "NGS_BIND_HOST=127.0.0.1",
			"NGS_GO_FRONT=1")
		started := time.Now()
		if err := cmd.Start(); err != nil {
			log.Printf("worker: cannot start %q: %v", w.argv[0], err)
			w.mu.Lock()
			w.lastExit = err.Error()
			w.mu.Unlock()
		} else {
			log.Printf("worker: pid %d on 127.0.0.1:%d", cmd.Process.Pid, w.port)
			w.mu.Lock()
			w.cmd = cmd
			w.mu.Unlock()
			err := cmd.Wait()
			w.mu.Lock()
			w.cmd = nil
			w.lastExit = fmt.Sprint(err)
			w.mu.Unlock()
			if w.stopping.Load() {
				return
			}
			log.Printf("worker: exited after %s: %v", time.Since(started).Round(time.Second), err)
		}
		if time.Since(started) > time.Minute {
			backoff = time.Second
		}
		w.mu.Lock()
		w.restarts++
		w.mu.Unlock()
		time.Sleep(backoff)
		if backoff < 30*time.Second {
			backoff *= 2
		}
	}
}

func (w *worker) stop(grace time.Duration) {
	w.stopping.Store(true)
	w.mu.Lock()
	cmd := w.cmd
	w.mu.Unlock()
	if cmd != nil && cmd.Process != nil {
		_ = cmd.Process.Signal(syscall.SIGTERM)
	}
	select {
	case <-w.done:
	case <-time.After(grace):
		if cmd != nil && cmd.Process != nil {
			_ = cmd.Process.Kill()
		}
	}
}

func freePort() (int, error) {
	l, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		return 0, err
	}
	defer l.Close()
	return l.Addr().(*net.TCPAddr).Port, nil
}

func main() {
	log.SetFlags(log.LstdFlags | log.LUTC)
	home, _ := os.UserHomeDir()
	listen := flag.String("listen", envOr("NGS_HOST", "127.0.0.1")+":"+envOr("NGS_PORT", "4444"), "address to listen on")
	vault := flag.String("vault", envOr("NOUGEN_VAULT_DIR", filepath.Join(home, ".nougen", "shards")), "vault directory")
	workerPort := flag.Int("worker-port", 0, "loopback port for the Python worker (0 = pick a free one)")
	flag.Parse()

	n := &node{token: os.Getenv("NGS_NODE_TOKEN"), index: newVectorIndex(*vault), start: time.Now()}
	for _, e := range n.index.refresh() {
		log.Printf("vector index: %v", e)
	}
	rows := 0
	for _, s := range n.index.status() {
		rows += s.Rows
	}
	log.Printf("vector index: %d DB(s), %d rows mapped from %s", len(n.index.status()), rows, n.index.dir)

	if argv := flag.Args(); len(argv) > 0 {
		port := *workerPort
		if port == 0 {
			var err error
			if port, err = freePort(); err != nil {
				log.Fatalf("no free loopback port for the worker: %v", err)
			}
		}
		n.worker = &worker{argv: argv, port: port, done: make(chan struct{})}
		n.proxy = newProxy(&url.URL{Scheme: "http", Host: fmt.Sprintf("127.0.0.1:%d", port)})
		go n.worker.run()
	}

	srv := &http.Server{Addr: *listen, Handler: n.routes(), ReadHeaderTimeout: 15 * time.Second}
	go func() {
		sig := make(chan os.Signal, 1)
		signal.Notify(sig, syscall.SIGTERM, syscall.SIGINT)
		<-sig
		log.Printf("shutting down")
		if n.worker != nil {
			n.worker.stop(15 * time.Second)
		}
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(ctx)
	}()
	log.Printf("ngsnode listening on %s (token %s)", *listen, map[bool]string{true: "set", false: "MISSING"}[n.token != ""])
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
