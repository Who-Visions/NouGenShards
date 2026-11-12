package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"testing"
	"time"
)

// TestMain lets the test binary stand in for a node or a tunnel: the
// supervisor under test starts real processes, not mocks.
func TestMain(m *testing.M) {
	switch os.Getenv("SUP_HELPER") {
	case "":
		os.Exit(m.Run())
	case "exit":
		os.Exit(3)
	default:
		code := http.StatusOK
		if os.Getenv("SUP_HELPER") == "sick" {
			code = http.StatusInternalServerError
		}
		mux := http.NewServeMux()
		answer := func(w http.ResponseWriter, _ *http.Request) { w.WriteHeader(code) }
		mux.HandleFunc("/health", answer)
		mux.HandleFunc("/ready", answer)
		_ = http.ListenAndServe(os.Getenv("SUP_ADDR"), mux)
		os.Exit(1)
	}
}

type fakeLauncher struct{ node, tunnel string }

func helper(mode, addr string) *exec.Cmd {
	cmd := exec.Command(os.Args[0])
	cmd.Env = append(os.Environ(), "SUP_HELPER="+mode, "SUP_ADDR="+addr)
	return cmd
}

func (f fakeLauncher) Node(n Node) *exec.Cmd {
	return helper(f.node, fmt.Sprintf("127.0.0.1:%d", n.Port))
}
func (f fakeLauncher) Tunnel(n Node, addr string) *exec.Cmd { return helper(f.tunnel, addr) }

func freePort(t *testing.T) int {
	t.Helper()
	// The tunnel's readiness port is derived from the node port; both must be free.
	for i := 0; i < 200; i++ {
		ln, err := net.Listen("tcp", "127.0.0.1:0")
		if err != nil {
			t.Fatal(err)
		}
		p := ln.Addr().(*net.TCPAddr).Port
		ln.Close()
		if m, err := net.Listen("tcp", metricsAddr(p)); err == nil {
			m.Close()
			return p
		}
	}
	t.Fatal("no free port pair")
	return 0
}

func writeNode(t *testing.T, base, id string, port int, tunnel string) {
	t.Helper()
	dir := filepath.Join(base, id)
	if err := os.MkdirAll(filepath.Join(dir, "NouGenShards"), 0o700); err != nil {
		t.Fatal(err)
	}
	os.WriteFile(filepath.Join(dir, "NouGenShards", "app.py"), nil, 0o600)
	b, _ := json.Marshal(Node{ID: id, Port: port, Token: "secret-token-value", Tunnel: tunnel, URL: "https://" + id + ".example"})
	os.WriteFile(filepath.Join(dir, "node.json"), b, 0o600)
}

func fastTiming() Timing {
	return Timing{Tick: 50 * time.Millisecond, NodeGrace: 3 * time.Second, TunnelGrace: 3 * time.Second,
		BackoffMin: 10 * time.Millisecond, BackoffMax: 80 * time.Millisecond, Stable: time.Hour,
		Probe: time.Second, Fails: 2}
}

func newTest(t *testing.T, l Launcher, tm Timing) (*Supervisor, string) {
	t.Helper()
	base := t.TempDir()
	s := NewSupervisor(base, tm, l, slog.New(slog.NewTextHandler(io.Discard, nil)))
	t.Cleanup(func() {
		for _, e := range s.entries {
			if e.n.proc.alive() {
				killTree(e.n.proc.cmd)
				<-e.n.proc.done
			}
			if e.tun.proc.alive() {
				killTree(e.tun.proc.cmd)
				<-e.tun.proc.done
			}
		}
	})
	return s, base
}

// tickUntil drives the supervisor with real time until cond holds.
func tickUntil(t *testing.T, s *Supervisor, what string, cond func() bool) {
	t.Helper()
	deadline := time.Now().Add(20 * time.Second)
	for time.Now().Before(deadline) {
		s.Tick(time.Now())
		if cond() {
			return
		}
		time.Sleep(40 * time.Millisecond)
	}
	t.Fatalf("timed out waiting for: %s (status %+v)", what, s.Snapshot())
}

func TestDiscoverReadsEveryLayout(t *testing.T) {
	base := t.TempDir()
	writeNode(t, base, "json-acct", 4446, "tun")

	ps := filepath.Join(base, "ps-acct")
	os.MkdirAll(filepath.Join(ps, "NouGenShards"), 0o700)
	os.WriteFile(filepath.Join(ps, "NouGenShards", "app.py"), nil, 0o600)
	os.WriteFile(filepath.Join(ps, "run.ps1"), []byte("$env:NGS_NODE_TOKEN = 'it''s'\r\n$env:NGS_PORT = '4444'\r\n"+
		"Start-Process -FilePath x -ArgumentList 'tunnel','--no-autoupdate','run','--token','TT'\r\n"), 0o600)

	sh := filepath.Join(base, "sh-acct")
	os.MkdirAll(filepath.Join(sh, "NouGenShards"), 0o700)
	os.WriteFile(filepath.Join(sh, "NouGenShards", "app.py"), nil, 0o600)
	os.WriteFile(filepath.Join(sh, "run.sh"), []byte("export NGS_NODE_TOKEN='abc' NGS_PORT='4445'\nnohup cloudflared tunnel run --token 'UU' &\n"), 0o600)

	// Half-finished download: described, but nothing to run.
	half := filepath.Join(base, "half")
	os.MkdirAll(half, 0o700)
	os.WriteFile(filepath.Join(half, "node.json"), []byte(`{"id":"half","port":4447,"token":"x"}`), 0o600)
	// Same port as an earlier folder: must not start a second copy.
	writeNode(t, base, "zz-dupe", 4446, "")
	// Not an account at all.
	os.MkdirAll(filepath.Join(base, "logs"), 0o700)
	// node.json written by PowerShell 5 carries a byte-order mark.
	bom := filepath.Join(base, "bom-acct")
	os.MkdirAll(filepath.Join(bom, "NouGenShards"), 0o700)
	os.WriteFile(filepath.Join(bom, "NouGenShards", "app.py"), nil, 0o600)
	os.WriteFile(filepath.Join(bom, "node.json"), []byte(utf8BOM+`{"id":"bom-acct","port":4448,"token":"x"}`), 0o600)

	// The earliest setup: the first account lives in base itself.
	os.MkdirAll(filepath.Join(base, "NouGenShards"), 0o700)
	os.WriteFile(filepath.Join(base, "NouGenShards", "app.py"), nil, 0o600)
	os.WriteFile(filepath.Join(base, "run.ps1"), []byte("$env:NGS_NODE_TOKEN = 'r'\r\n$env:NGS_HUD_USER = 'first'\r\n$env:NGS_PORT = '4443'\r\n"), 0o600)

	got := Discover(base)
	var ids []string
	for _, n := range got {
		ids = append(ids, fmt.Sprintf("%s:%d:%s", n.ID, n.Port, n.Source))
	}
	want := "first:4443:run.ps1 ps-acct:4444:run.ps1 sh-acct:4445:run.sh json-acct:4446:node.json bom-acct:4448:node.json"
	if strings.Join(ids, " ") != want {
		t.Fatalf("got  %s\nwant %s", strings.Join(ids, " "), want)
	}
	if got[1].Token != "it's" || got[1].Tunnel != "TT" || got[2].Tunnel != "UU" || got[0].Dir != base {
		t.Fatalf("legacy layouts not read: %+v %+v %+v", got[0], got[1], got[2])
	}
}

func TestStartsThenRestartsADeadNodeAndTunnel(t *testing.T) {
	s, base := newTest(t, fakeLauncher{node: "ok", tunnel: "ok"}, fastTiming())
	writeNode(t, base, "acct", freePort(t), "tunnel-token")
	up := func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up" && st.Nodes[0].Tunnel.State == "up"
	}
	tickUntil(t, s, "first start", up)

	e := s.entries["acct"]
	oldNode, oldTun := e.n.proc, e.tun.proc
	killTree(oldNode.cmd)
	killTree(oldTun.cmd)
	<-oldNode.done
	<-oldTun.done

	tickUntil(t, s, "restart after kill", func() bool {
		return up() && e.n.proc != oldNode && e.tun.proc != oldTun
	})
	if e.n.restarts != 2 || e.tun.restarts != 2 {
		t.Fatalf("starts: node %d tunnel %d, want 2 and 2", e.n.restarts, e.tun.restarts)
	}
}

func TestAHungNodeIsStoppedAfterItsGrace(t *testing.T) {
	tm := fastTiming()
	tm.NodeGrace = 300 * time.Millisecond
	s, base := newTest(t, fakeLauncher{node: "sick"}, tm)
	writeNode(t, base, "acct", freePort(t), "")
	e := func() *entry { return s.entries["acct"] }
	tickUntil(t, s, "first start", func() bool { return e() != nil && e().n.proc.alive() })
	first := e().n.proc
	tickUntil(t, s, "hung node replaced", func() bool { return e().n.proc != first && e().n.restarts >= 2 })
	select {
	case <-first.done:
	case <-time.After(5 * time.Second):
		t.Fatal("the hung node was never stopped")
	}
	if st := s.Snapshot().Nodes[0].Tunnel.State; st != "none" {
		t.Fatalf("an account with no tunnel reported %q", st)
	}
}

func TestAFailingNodeBacksOffInsteadOfSpinning(t *testing.T) {
	tm := fastTiming()
	tm.BackoffMin, tm.BackoffMax = time.Minute, 4*time.Minute
	s, base := newTest(t, fakeLauncher{node: "exit"}, tm)
	writeNode(t, base, "acct", freePort(t), "")
	now := time.Now()
	for i := 0; i < 6; i++ { // same instant: at most one start
		s.Tick(now)
		time.Sleep(60 * time.Millisecond)
	}
	e := s.entries["acct"]
	if e.n.restarts != 1 {
		t.Fatalf("started %d times within one backoff window, want 1", e.n.restarts)
	}
	s.Tick(now.Add(61 * time.Second))
	if e.n.restarts != 2 {
		t.Fatalf("after the first wait: %d starts, want 2", e.n.restarts)
	}
	s.Tick(now.Add(62 * time.Second)) // second wait is two minutes
	if e.n.restarts != 2 {
		t.Fatalf("restarted before the doubled wait: %d starts", e.n.restarts)
	}
}

func TestAnAdoptedNodeIsNotDoubleStarted(t *testing.T) {
	s, base := newTest(t, fakeLauncher{node: "ok"}, fastTiming())
	port := freePort(t)
	writeNode(t, base, "acct", port, "")
	// A node someone else started (an older launcher) is already answering.
	srv := &http.Server{Addr: fmt.Sprintf("127.0.0.1:%d", port), Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {})}
	go srv.ListenAndServe()
	defer srv.Close()
	tickUntil(t, s, "adopted", func() bool { st := s.Snapshot(); return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up" })
	if s.entries["acct"].n.restarts != 0 {
		t.Fatal("started a second node beside a healthy one")
	}
}

func TestABusyPortIsReportedNotFought(t *testing.T) {
	s, base := newTest(t, fakeLauncher{node: "ok"}, fastTiming())
	port := freePort(t)
	writeNode(t, base, "acct", port, "")
	srv := &http.Server{Addr: fmt.Sprintf("127.0.0.1:%d", port), Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		w.WriteHeader(http.StatusNotFound) // some other program
	})}
	go srv.ListenAndServe()
	defer srv.Close()
	tickUntil(t, s, "port-busy", func() bool { st := s.Snapshot(); return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "port-busy" })
	if s.entries["acct"].n.restarts != 0 {
		t.Fatal("tried to start a node on a port another program holds")
	}
}

func TestARemovedAccountIsStopped(t *testing.T) {
	s, base := newTest(t, fakeLauncher{node: "ok"}, fastTiming())
	writeNode(t, base, "acct", freePort(t), "")
	tickUntil(t, s, "up", func() bool { st := s.Snapshot(); return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up" })
	p := s.entries["acct"].n.proc
	if err := os.Remove(filepath.Join(base, "acct", "node.json")); err != nil {
		t.Fatal(err)
	}
	s.Tick(time.Now())
	select {
	case <-p.done:
	case <-time.After(5 * time.Second):
		t.Fatal("node of a removed account kept running")
	}
	if len(s.entries) != 0 {
		t.Fatal("removed account still tracked")
	}
}

func TestControlEndpointKeepsSecretsAndRefusesWebPages(t *testing.T) {
	s, base := newTest(t, fakeLauncher{node: "ok", tunnel: "ok"}, fastTiming())
	writeNode(t, base, "acct", freePort(t), "tunnel-credential")
	tickUntil(t, s, "up", func() bool { st := s.Snapshot(); return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up" })

	quit := make(chan struct{}, 1)
	h := handler(s, "127.0.0.1:47411", func() { quit <- struct{}{} })
	do := func(method, path, host string, hdr bool) *httptest.ResponseRecorder {
		r := httptest.NewRequest(method, path, nil)
		r.Host = host
		if hdr {
			r.Header.Set(guardHeader, "1")
		}
		w := httptest.NewRecorder()
		h.ServeHTTP(w, r)
		return w
	}
	st := do("GET", "/status", "127.0.0.1:47411", false)
	body := st.Body.String()
	if st.Code != 200 || !strings.Contains(body, `"acct"`) {
		t.Fatalf("status: %d %s", st.Code, body)
	}
	if strings.Contains(body, "secret-token-value") || strings.Contains(body, "tunnel-credential") {
		t.Fatalf("status leaks a credential: %s", body)
	}
	for name, w := range map[string]*httptest.ResponseRecorder{
		"rebound host":   do("GET", "/status", "evil.example", false),
		"quit by GET":    do("GET", "/quit", "127.0.0.1:47411", true),
		"quit no header": do("POST", "/quit", "127.0.0.1:47411", false), // what a web page can send
		"quit bad host":  do("POST", "/quit", "evil.example", true),
	} {
		if w.Code != http.StatusForbidden {
			t.Errorf("%s: got %d, want 403", name, w.Code)
		}
	}
	select {
	case <-quit:
		t.Fatal("a refused request stopped the supervisor")
	default:
	}
	if w := do("POST", "/quit", "127.0.0.1:47411", true); w.Code != 200 {
		t.Fatalf("legitimate quit: %d", w.Code)
	}
	select {
	case <-quit:
	case <-time.After(2 * time.Second):
		t.Fatal("quit did not fire")
	}
}

func TestTunnelCredentialNeverAppearsInArguments(t *testing.T) {
	n := Node{ID: "a", Port: 4444, Token: "node-secret", Tunnel: "tunnel-secret", Dir: t.TempDir()}
	l := realLauncher{base: t.TempDir()}
	for _, cmd := range []*exec.Cmd{l.Tunnel(n, "127.0.0.1:24444"), l.Node(n)} {
		for _, a := range cmd.Args {
			if strings.Contains(a, "secret") {
				t.Fatalf("credential in arguments: %v", cmd.Args)
			}
		}
	}
	if !strings.Contains(strings.Join(l.Tunnel(n, "x").Env, "\n"), "TUNNEL_TOKEN=tunnel-secret") {
		t.Fatal("tunnel credential not passed in the environment")
	}
	nodeEnv := strings.Join(l.Node(n).Env, "\n")
	for _, want := range []string{
		"NOUGEN_VAULT_DIR=" + filepath.Join(n.Dir, "shards"),
		"NOUGEN_HOME=" + n.Dir,
		"NOUGEN_ROOT=" + n.Dir,
		"NOUGEN_SECRETS_VAULT_DIR=" + filepath.Join(n.Dir, "secrets"),
	} {
		if !strings.Contains(nodeEnv, want) {
			t.Fatalf("node env missing %q", want)
		}
	}
}

func TestSnapshotDoesNotBlockDuringSlowProbes(t *testing.T) {
	started := make(chan struct{}, 1)
	release := make(chan struct{})
	releaseOnce := sync.OnceFunc(func() { close(release) })
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		select {
		case started <- struct{}{}:
		default:
		}
		<-release
	}))
	defer func() {
		releaseOnce()
		srv.Close()
	}()
	_, portStr, _ := net.SplitHostPort(srv.Listener.Addr().String())
	var port int
	fmt.Sscanf(portStr, "%d", &port)

	tm := fastTiming()
	tm.Probe = 2 * time.Second
	s, base := newTest(t, fakeLauncher{node: "ok"}, tm)
	writeNode(t, base, "acct", port, "")

	done := make(chan struct{})
	go func() {
		s.Tick(time.Now())
		close(done)
	}()
	<-started

	snapStart := time.Now()
	_ = s.Snapshot()
	if elapsed := time.Since(snapStart); elapsed > 200*time.Millisecond {
		t.Fatalf("Snapshot blocked %v behind slow Tick probe", elapsed)
	}
	releaseOnce()
	<-done
}

func TestCmdStatusJSONPreservesUnhealthyExitCode(t *testing.T) {
	tm := fastTiming()
	tm.NodeGrace = time.Hour
	s, base := newTest(t, fakeLauncher{node: "sick"}, tm)
	writeNode(t, base, "acct", freePort(t), "")
	s.Tick(time.Now())

	srv := httptest.NewServer(nil)
	srv.Config.Handler = handler(s, srv.Listener.Addr().String(), func() {})
	defer srv.Close()
	t.Setenv("NOUGEN_SUPERVISOR_ADDR", srv.Listener.Addr().String())

	var out bytes.Buffer
	code := cmdStatus(&out, true)
	if code != 2 {
		t.Fatalf("cmdStatus(-json) with unhealthy node returned %d, want 2 (body: %s)", code, out.String())
	}
	if !strings.Contains(out.String(), `"running":true`) || !strings.Contains(out.String(), `"acct"`) {
		t.Fatalf("unexpected status JSON: %s", out.String())
	}
}

func TestOwnLogRotatesAtItsCap(t *testing.T) {
	path := filepath.Join(t.TempDir(), "supervisor.log")
	r := &rotatingFile{path: path, max: 100}
	for i := 0; i < 10; i++ {
		if _, err := r.Write([]byte(strings.Repeat("x", 30) + "\n")); err != nil {
			t.Fatal(err)
		}
	}
	r.f.Close()
	cur, _ := os.Stat(path)
	old, err := os.Stat(path + ".1")
	if err != nil || cur.Size() > 100 || old.Size() > 100 {
		t.Fatalf("rotation: current %v, previous %v err %v", cur.Size(), old, err)
	}
}
