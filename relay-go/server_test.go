package main

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

const testToken = "test-token"

func newRelay(t *testing.T, cfg Config) (*httptest.Server, *MemStore, *Server) {
	t.Helper()
	st := NewMemStore()
	_ = st.Put("n1", sha256Hex(testToken))
	_ = st.Put("n2", sha256Hex("other-token"))
	srv := NewServer(cfg, st)
	ts := httptest.NewServer(srv)
	t.Cleanup(ts.Close)
	return ts, st, srv
}

func wsURL(ts *httptest.Server, path string) string {
	return "ws" + strings.TrimPrefix(ts.URL, "http") + path
}

// dialNode connects as a node and returns the socket and its ready frame.
func dialNode(t *testing.T, ts *httptest.Server, id, token string) (*websocket.Conn, readyFrame) {
	t.Helper()
	h := http.Header{}
	if token != "" {
		h.Set("Authorization", "Bearer "+token)
	}
	c, resp, err := websocket.DefaultDialer.Dial(wsURL(ts, "/_relay/connect?id="+id), h)
	if err != nil {
		code := 0
		if resp != nil {
			code = resp.StatusCode
		}
		t.Fatalf("dial %s: %v (status %d)", id, err, code)
	}
	t.Cleanup(func() { c.Close() })
	var ready readyFrame
	if err := c.ReadJSON(&ready); err != nil {
		t.Fatalf("read ready: %v", err)
	}
	return c, ready
}

// serveNode answers every req frame with whatever reply builds, until the socket closes.
func serveNode(c *websocket.Conn, reply func(reqFrame) map[string]any) {
	go func() {
		for {
			_, msg, err := c.ReadMessage()
			if err != nil {
				return
			}
			var head struct{ T string }
			_ = json.Unmarshal(msg, &head)
			if head.T != "req" {
				continue
			}
			var rq reqFrame
			_ = json.Unmarshal(msg, &rq)
			if out := reply(rq); out != nil {
				out["t"], out["rid"] = "res", rq.Rid
				_ = c.WriteJSON(out)
			}
		}
	}()
}

func b64(s string) string { return base64.StdEncoding.EncodeToString([]byte(s)) }

func get(t *testing.T, ts *httptest.Server, method, path, host string, body io.Reader) (*http.Response, string) {
	t.Helper()
	req, _ := http.NewRequest(method, ts.URL+path, body)
	if host != "" {
		req.Host = host
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatalf("%s %s: %v", method, path, err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}

func okReply(body string) func(reqFrame) map[string]any {
	return func(reqFrame) map[string]any {
		return map[string]any{"status": 200, "headers": [][]string{{"content-type", "text/plain"}}, "body": b64(body)}
	}
}

func TestHealth(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	resp, body := get(t, ts, "GET", "/_relay/health", "", nil)
	if resp.StatusCode != 200 || body != "ok" {
		t.Fatalf("health: %d %q", resp.StatusCode, body)
	}
}

func TestConnectAuth(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	cases := []struct {
		name, path, auth string
		want             int
	}{
		{"no token", "/_relay/connect?id=n1", "", 401},
		{"wrong token", "/_relay/connect?id=n1", "Bearer nope", 401},
		{"another node's token", "/_relay/connect?id=n1", "Bearer other-token", 401},
		{"unknown id", "/_relay/connect?id=ghost", "Bearer " + testToken, 401},
		{"bad id", "/_relay/connect?id=BAD_ID!", "Bearer " + testToken, 400},
		{"missing id", "/_relay/connect", "Bearer " + testToken, 400},
		{"not a websocket", "/_relay/connect?id=n1", "Bearer " + testToken, 426},
		{"status needs a token too", "/_relay/status?id=n1", "", 401},
	}
	for _, c := range cases {
		req, _ := http.NewRequest("GET", ts.URL+c.path, nil)
		if c.auth != "" {
			req.Header.Set("Authorization", c.auth)
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		resp.Body.Close()
		if resp.StatusCode != c.want {
			t.Errorf("%s: got %d want %d", c.name, resp.StatusCode, c.want)
		}
	}
	// ids are case-insensitive, like the Worker (it lower-cases before the lookup)
	dialNode(t, ts, "N1", testToken)
}

func TestRoundTripViaPathAndHostSuffix(t *testing.T) {
	ts, _, _ := newRelay(t, Config{HostSuffix: ".relay.test"})
	c, ready := dialNode(t, ts, "n1", testToken)
	if ready.T != "ready" || ready.V != Protocol || ready.Since <= 0 {
		t.Fatalf("ready frame: %+v", ready)
	}
	var mu sync.Mutex
	var seen reqFrame
	serveNode(c, func(rq reqFrame) map[string]any {
		mu.Lock()
		seen = rq
		mu.Unlock()
		return map[string]any{"status": 201, "headers": [][]string{{"content-type", "text/plain"}, {"x-a", "1"}, {"x-a", "2"}, {"connection", "close"}},
			"body": b64("hello " + rq.Path)}
	})

	resp, body := get(t, ts, "POST", "/n/n1/api/x?y=1&z=%2F", "", strings.NewReader("payload"))
	if resp.StatusCode != 201 || body != "hello /api/x?y=1&z=%2F" {
		t.Fatalf("path route: %d %q", resp.StatusCode, body)
	}
	if resp.Header.Get("x-nougen-transport") != "relay" {
		t.Error("response must carry x-nougen-transport: relay")
	}
	if got := resp.Header.Values("x-a"); len(got) != 2 || got[0] != "1" || got[1] != "2" {
		t.Errorf("repeated headers must survive: %v", got)
	}
	if resp.Header.Get("connection") == "close" {
		t.Error("hop-by-hop header from the node must be dropped")
	}
	mu.Lock()
	rq := seen
	mu.Unlock()
	if rq.Method != "POST" || rq.Path != "/api/x?y=1&z=%2F" || rq.Rid == "" {
		t.Errorf("req frame: %+v", rq)
	}
	if raw, _ := base64.StdEncoding.DecodeString(rq.Body); string(raw) != "payload" {
		t.Errorf("req body: %q", rq.Body)
	}
	for k := range rq.Headers {
		if hop[strings.ToLower(k)] {
			t.Errorf("hop-by-hop header %q reached the node", k)
		}
	}

	// the bare /n/<id> form is the root path
	_, body = get(t, ts, "GET", "/n/n1", "", nil)
	if body != "hello /" {
		t.Errorf("bare /n/n1: %q", body)
	}
	// host-suffix form
	_, body = get(t, ts, "GET", "/mcp", "n1.relay.test", nil)
	if body != "hello /mcp" {
		t.Errorf("host suffix: %q", body)
	}
	_, body = get(t, ts, "GET", "/mcp", "n1.relay.test:8443", nil)
	if body != "hello /mcp" {
		t.Errorf("host suffix with port: %q", body)
	}
}

func TestRoutingMisses(t *testing.T) {
	ts, _, _ := newRelay(t, Config{HostSuffix: ".relay.test"})
	for _, c := range []struct{ path, host string }{
		{"/", ""}, {"/n/BAD_ID/x", ""}, {"/n/", ""}, {"/other", "evil.example"}, {"/x", "-bad.relay.test"},
	} {
		resp, _ := get(t, ts, "GET", c.path, c.host, nil)
		if resp.StatusCode != 404 {
			t.Errorf("%+v: got %d want 404", c, resp.StatusCode)
		}
	}
}

func TestOfflineNode(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	resp, body := get(t, ts, "GET", "/n/n1/x", "", nil)
	if resp.StatusCode != 502 || !strings.Contains(body, "offline") || !strings.Contains(body, "n1") {
		t.Fatalf("offline: %d %q", resp.StatusCode, body)
	}
	if resp.Header.Get("cache-control") != "no-store" {
		t.Error("offline page must not be cached")
	}
}

func TestStatus(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	status := func() map[string]any {
		req, _ := http.NewRequest("GET", ts.URL+"/_relay/status?id=n1", nil)
		req.Header.Set("Authorization", "Bearer "+testToken)
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		var m map[string]any
		_ = json.NewDecoder(resp.Body).Decode(&m)
		return m
	}
	m := status()
	if m["live"] != false || m["transport"] != "relay" || m["since"] != nil {
		t.Fatalf("offline status: %v", m)
	}
	_, ready := dialNode(t, ts, "n1", testToken)
	m = status()
	if m["live"] != true || int64(m["since"].(float64)) != ready.Since {
		t.Fatalf("live status: %v (ready since %d)", m, ready.Since)
	}
}

func TestReplaceClosesOldWithCode4000AndFailsItsRequests(t *testing.T) {
	ts, _, _ := newRelay(t, Config{Timeout: 5 * time.Second})
	old, _ := dialNode(t, ts, "n1", testToken)
	// the old node never answers, so a request is left in flight
	done := make(chan int, 1)
	go func() {
		resp, _ := get(t, ts, "GET", "/n/n1/slow", "", nil)
		done <- resp.StatusCode
	}()
	time.Sleep(150 * time.Millisecond)

	fresh, _ := dialNode(t, ts, "n1", testToken)
	serveNode(fresh, okReply("from the new node"))

	closeCode := make(chan int, 1)
	go func() {
		for {
			if _, _, err := old.ReadMessage(); err != nil {
				if ce, ok := err.(*websocket.CloseError); ok {
					closeCode <- ce.Code
				} else {
					closeCode <- -1
				}
				return
			}
		}
	}()
	select {
	case code := <-closeCode:
		if code != CloseReplaced {
			t.Errorf("old socket closed with %d, want %d", code, CloseReplaced)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("old socket was not closed")
	}
	select {
	case code := <-done:
		if code != 504 {
			t.Errorf("in-flight request on the replaced session: %d, want 504", code)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("in-flight request was not failed on replace")
	}
	_, body := get(t, ts, "GET", "/n/n1/x", "", nil)
	if body != "from the new node" {
		t.Errorf("the new node should serve: %q", body)
	}
}

func TestDisconnectFailsPendingAndGoesOffline(t *testing.T) {
	ts, _, _ := newRelay(t, Config{Timeout: 5 * time.Second})
	c, _ := dialNode(t, ts, "n1", testToken)
	done := make(chan int, 1)
	go func() {
		resp, _ := get(t, ts, "GET", "/n/n1/x", "", nil)
		done <- resp.StatusCode
	}()
	time.Sleep(150 * time.Millisecond)
	c.Close()
	select {
	case code := <-done:
		if code != 504 {
			t.Errorf("got %d want 504", code)
		}
	case <-time.After(3 * time.Second):
		t.Fatal("pending request not failed after the node left")
	}
	time.Sleep(100 * time.Millisecond)
	if resp, _ := get(t, ts, "GET", "/n/n1/x", "", nil); resp.StatusCode != 502 {
		t.Errorf("after disconnect want the offline 502, got %d", resp.StatusCode)
	}
}

func TestTimeout504(t *testing.T) {
	ts, _, _ := newRelay(t, Config{Timeout: 200 * time.Millisecond})
	c, _ := dialNode(t, ts, "n1", testToken)
	serveNode(c, func(reqFrame) map[string]any { return nil }) // never answers
	start := time.Now()
	resp, body := get(t, ts, "GET", "/n/n1/x", "", nil)
	if resp.StatusCode != 504 || !strings.Contains(body, "did not answer") {
		t.Fatalf("timeout: %d %q", resp.StatusCode, body)
	}
	if time.Since(start) > 3*time.Second {
		t.Error("timeout took far too long")
	}
}

func TestRequestBodyCap(t *testing.T) {
	ts, _, _ := newRelay(t, Config{MaxBody: 16})
	c, _ := dialNode(t, ts, "n1", testToken)
	serveNode(c, okReply("ok"))
	// declared length over the cap
	if resp, _ := get(t, ts, "POST", "/n/n1/x", "", strings.NewReader(strings.Repeat("a", 17))); resp.StatusCode != 413 {
		t.Errorf("declared: got %d want 413", resp.StatusCode)
	}
	// undeclared (chunked) length over the cap
	if resp, _ := get(t, ts, "POST", "/n/n1/x", "", io.NopCloser(strings.NewReader(strings.Repeat("a", 17)))); resp.StatusCode != 413 {
		t.Errorf("chunked: got %d want 413", resp.StatusCode)
	}
	if resp, _ := get(t, ts, "POST", "/n/n1/x", "", strings.NewReader(strings.Repeat("a", 16))); resp.StatusCode != 200 {
		t.Errorf("exactly at the cap: got %d want 200", resp.StatusCode)
	}
}

func TestNodeResponseIsNotTrusted(t *testing.T) {
	ts, _, _ := newRelay(t, Config{MaxBody: 16})
	c, _ := dialNode(t, ts, "n1", testToken)
	var mu sync.Mutex
	next := map[string]any{}
	serveNode(c, func(reqFrame) map[string]any {
		mu.Lock()
		defer mu.Unlock()
		out := map[string]any{}
		for k, v := range next {
			out[k] = v
		}
		return out
	})
	set := func(m map[string]any) { mu.Lock(); next = m; mu.Unlock() }

	cases := []struct {
		name string
		resp map[string]any
		want int
	}{
		{"status 99", map[string]any{"status": 99, "body": b64("x")}, 502},
		{"status 600", map[string]any{"status": 600, "body": b64("x")}, 502},
		{"status fractional", map[string]any{"status": 200.5, "body": b64("x")}, 502},
		{"status a string", map[string]any{"status": "200", "body": b64("x")}, 502},
		{"status missing", map[string]any{"body": b64("x")}, 502},
		{"body not a string", map[string]any{"status": 200, "body": 5}, 502},
		{"body not base64", map[string]any{"status": 200, "body": "***"}, 502},
		{"headers a string", map[string]any{"status": 200, "headers": "x", "body": b64("x")}, 502},
		{"header pair wrong length", map[string]any{"status": 200, "headers": [][]string{{"a"}}, "body": b64("x")}, 502},
		{"header value not a string", map[string]any{"status": 200, "headers": map[string]any{"a": 1}, "body": b64("x")}, 502},
		{"header name with a space", map[string]any{"status": 200, "headers": [][]string{{"bad name", "v"}}, "body": b64("x")}, 502},
		{"header value with a newline", map[string]any{"status": 200, "headers": [][]string{{"x-a", "v\r\nset-cookie: pwn=1"}}, "body": b64("x")}, 502},
		{"response over the cap", map[string]any{"status": 200, "body": b64(strings.Repeat("a", 17))}, 502},
		{"headers as an object", map[string]any{"status": 200, "headers": map[string]any{"x-obj": "yes"}, "body": b64("x")}, 200},
		{"null headers and body", map[string]any{"status": 200, "headers": nil, "body": nil}, 200},
		{"exactly at the cap", map[string]any{"status": 200, "body": b64(strings.Repeat("a", 16))}, 200},
	}
	for _, tc := range cases {
		set(tc.resp)
		resp, _ := get(t, ts, "GET", "/n/n1/x", "", nil)
		if resp.StatusCode != tc.want {
			t.Errorf("%s: got %d want %d", tc.name, resp.StatusCode, tc.want)
		}
	}
	set(map[string]any{"status": 200, "headers": map[string]any{"x-obj": "yes"}, "body": b64("x")})
	if resp, _ := get(t, ts, "GET", "/n/n1/x", "", nil); resp.Header.Get("x-obj") != "yes" {
		t.Error("a plain header object must still be accepted")
	}
}

func TestNullBodyStatusesAndHead(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	c, _ := dialNode(t, ts, "n1", testToken)
	serveNode(c, func(rq reqFrame) map[string]any {
		st := 200
		switch rq.Path {
		case "/204":
			st = 204
		case "/304":
			st = 304
		}
		return map[string]any{"status": st, "body": b64("should not be sent")}
	})
	for _, p := range []string{"/204", "/304"} {
		resp, body := get(t, ts, "GET", "/n/n1"+p, "", nil)
		if body != "" {
			t.Errorf("%s must have no body, got %q", p, body)
		}
		_ = resp
	}
	if _, body := get(t, ts, "HEAD", "/n/n1/x", "", nil); body != "" {
		t.Errorf("HEAD must have no body, got %q", body)
	}
}

func TestHeartbeat(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	c, _ := dialNode(t, ts, "n1", testToken)
	_ = c.WriteMessage(websocket.TextMessage, []byte(`{"t":"ping"}`))
	_ = c.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, msg, err := c.ReadMessage()
	if err != nil || string(msg) != `{"t":"pong"}` {
		t.Fatalf("heartbeat: %q %v", msg, err)
	}
	// junk and unknown frames are ignored, the socket stays up
	_ = c.WriteMessage(websocket.TextMessage, []byte(`not json`))
	_ = c.WriteMessage(websocket.TextMessage, []byte(`{"t":"nope"}`))
	_ = c.WriteMessage(websocket.TextMessage, []byte(`{"t":"res","rid":"unknown","status":200}`))
	_ = c.WriteMessage(websocket.TextMessage, []byte(`{"t":"ping"}`))
	if _, msg, err = c.ReadMessage(); err != nil || string(msg) != `{"t":"pong"}` {
		t.Fatalf("still alive after junk: %q %v", msg, err)
	}
}

func TestIdleNodeIsDropped(t *testing.T) {
	ts, _, srv := newRelay(t, Config{IdleTimeout: 300 * time.Millisecond})
	c, _ := dialNode(t, ts, "n1", testToken)
	_ = c.SetReadDeadline(time.Now().Add(3 * time.Second))
	if _, _, err := c.ReadMessage(); err == nil {
		t.Fatal("a silent node should be disconnected")
	}
	time.Sleep(100 * time.Millisecond)
	if srv.hub.liveCount() != 0 {
		t.Error("the dropped node must leave the hub")
	}
}

func TestConcurrentRequestsGetTheirOwnAnswers(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	c, _ := dialNode(t, ts, "n1", testToken)
	serveNode(c, func(rq reqFrame) map[string]any {
		return map[string]any{"status": 200, "body": b64("echo:" + rq.Path)}
	})
	var wg sync.WaitGroup
	for i := 0; i < 40; i++ {
		wg.Add(1)
		go func(i int) {
			defer wg.Done()
			p := "/p" + string(rune('a'+i%26)) + strings.Repeat("x", i)
			_, body := get(t, ts, "GET", "/n/n1"+p, "", nil)
			if body != "echo:"+p {
				t.Errorf("request %d got %q", i, body)
			}
		}(i)
	}
	wg.Wait()
}

func TestLargeBodyRoundTrip(t *testing.T) {
	ts, _, _ := newRelay(t, Config{MaxBody: 1 << 20})
	c, _ := dialNode(t, ts, "n1", testToken)
	serveNode(c, func(rq reqFrame) map[string]any {
		return map[string]any{"status": 200, "body": rq.Body} // echo the base64 body back
	})
	payload := bytes.Repeat([]byte{0, 1, 2, 250, 255}, 150_000) // 750 KB of binary
	req, _ := http.NewRequest("POST", ts.URL+"/n/n1/echo", bytes.NewReader(payload))
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	got, _ := io.ReadAll(resp.Body)
	if resp.StatusCode != 200 || !bytes.Equal(got, payload) {
		t.Fatalf("binary round trip failed: %d, %d bytes back", resp.StatusCode, len(got))
	}
}

func TestAuthStoreFailureFailsClosed(t *testing.T) {
	srv := NewServer(Config{}, failingStore{})
	ts := httptest.NewServer(srv)
	defer ts.Close()
	req, _ := http.NewRequest("GET", ts.URL+"/_relay/status?id=n1", nil)
	req.Header.Set("Authorization", "Bearer "+testToken)
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	resp.Body.Close()
	if resp.StatusCode != 503 {
		t.Errorf("a broken auth store must not let anyone in: got %d", resp.StatusCode)
	}
}

type failingStore struct{}

func (failingStore) Hash(string) (string, bool, error) { return "", false, io.ErrUnexpectedEOF }
func (failingStore) Put(string, string) error          { return io.ErrUnexpectedEOF }
func (failingStore) IDs() ([]string, error)            { return nil, io.ErrUnexpectedEOF }
func (failingStore) Close() error                      { return nil }
