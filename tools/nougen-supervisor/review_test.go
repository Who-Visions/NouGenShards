package main

// Regression tests for the review of PR #1029 (2026-11-11).

import (
	"fmt"
	"net/http"
	"os"
	"path/filepath"
	"testing"
	"time"
)

// A node started by an older launcher that later hangs must be replaced, not
// reported as "port-busy" forever. It is recognised by running out of the
// account's own folder.
func TestAHungNodeFromAnOlderLauncherIsStoppedAndReplaced(t *testing.T) {
	tm := fastTiming()
	tm.NodeGrace = 300 * time.Millisecond
	s, base := newTest(t, fakeLauncher{node: "ok"}, tm)
	port := freePort(t)
	writeNode(t, base, "acct", port, "")

	old := helper("sick", fmt.Sprintf("127.0.0.1:%d", port))
	// What an older launcher's node looks like from outside: its command
	// line names app.py inside the account folder.
	old.Args = append(old.Args, filepath.Join(base, "acct", "NouGenShards", "app.py"))
	if err := old.Start(); err != nil {
		t.Fatal(err)
	}
	gone := make(chan struct{})
	go func() { _ = old.Wait(); close(gone) }()
	t.Cleanup(func() { _ = old.Process.Kill() })
	waitListening(t, port)

	tickUntil(t, s, "hung older node replaced by a healthy one", func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up"
	})
	select {
	case <-gone:
	case <-time.After(5 * time.Second):
		t.Fatal("the hung older node is still running")
	}
	if got := s.entries["acct"].n.restarts; got != 1 {
		t.Fatalf("starts = %d, want exactly 1", got)
	}
}

func waitListening(t *testing.T, port int) {
	t.Helper()
	for i := 0; i < 100; i++ {
		if portOpen(port, 200*time.Millisecond) {
			return
		}
		time.Sleep(50 * time.Millisecond)
	}
	t.Fatalf("nothing came up on port %d", port)
}

// With no internet, a tunnel that cannot connect is left alone: restarting
// it changes nothing and cloudflared reconnects by itself.
func TestAnOfflineComputerDoesNotRestartItsTunnel(t *testing.T) {
	tm := fastTiming()
	tm.TunnelGrace = 200 * time.Millisecond
	s, base := newTest(t, fakeLauncher{node: "ok", tunnel: "sick"}, tm)
	s.Online = func() bool { return false }
	writeNode(t, base, "acct", freePort(t), "tunnel-token")

	tickUntil(t, s, "offline", func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Tunnel.State == "offline"
	})
	e := s.entries["acct"]
	first := e.tun.proc
	for i := 0; i < 15; i++ {
		s.Tick(time.Now())
		time.Sleep(40 * time.Millisecond)
	}
	if e.tun.proc != first || e.tun.restarts != 1 || !first.alive() {
		t.Fatalf("tunnel was restarted while offline: starts=%d", e.tun.restarts)
	}

	// Back online and still not connected: now it is the tunnel's fault.
	s.Online = func() bool { return true }
	tickUntil(t, s, "restart once online", func() bool { return e.tun.restarts >= 2 })
}

// While setup replaces an account's files it drops an "updating" file. The
// supervisor must not restart that account, even if its node stops and its
// code briefly disappears, and must pick it up again afterwards.
func TestAnAccountBeingUpdatedIsLeftAlone(t *testing.T) {
	s, base := newTest(t, fakeLauncher{node: "ok"}, fastTiming())
	writeNode(t, base, "acct", freePort(t), "")
	up := func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up"
	}
	tickUntil(t, s, "up", up)
	e := s.entries["acct"]

	marker := filepath.Join(base, "acct", "updating")
	if err := os.WriteFile(marker, nil, 0o600); err != nil {
		t.Fatal(err)
	}
	p := e.n.proc
	killGroup(p) // setup stops the account's processes
	<-p.done
	app := filepath.Join(base, "acct", "NouGenShards", "app.py")
	os.Remove(app) // ...and swaps its code
	for i := 0; i < 10; i++ {
		s.Tick(time.Now())
		time.Sleep(30 * time.Millisecond)
	}
	if e.n.restarts != 1 || s.entries["acct"] == nil {
		t.Fatalf("held account was touched: starts=%d tracked=%v", e.n.restarts, s.entries["acct"] != nil)
	}
	os.WriteFile(app, nil, 0o600)
	s.Tick(time.Now())
	if st := s.Snapshot().Nodes[0].Node.State; st != "updating" {
		t.Fatalf("state while held = %q, want updating", st)
	}

	os.Remove(marker)
	tickUntil(t, s, "back after the update", func() bool { return up() && e.n.restarts == 2 })
}

// A stale "updating" file (setup crashed) must not park an account forever.
func TestAStaleUpdateMarkerExpires(t *testing.T) {
	tm := fastTiming()
	tm.Hold = 50 * time.Millisecond
	s, base := newTest(t, fakeLauncher{node: "ok"}, tm)
	writeNode(t, base, "acct", freePort(t), "")
	os.WriteFile(filepath.Join(base, "acct", "updating"), nil, 0o600)
	time.Sleep(80 * time.Millisecond)
	tickUntil(t, s, "started despite a stale marker", func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Node.State == "up"
	})
}

// /status must answer immediately even while a check is stuck on a node
// that accepts connections and never replies.
func TestStatusNeverWaitsOnACheck(t *testing.T) {
	tm := fastTiming()
	tm.Probe = 2 * time.Second
	s, base := newTest(t, fakeLauncher{node: "ok"}, tm)
	port := freePort(t)
	writeNode(t, base, "acct", port, "")
	entered := make(chan struct{}, 1)
	release := make(chan struct{})
	srv := &http.Server{Addr: fmt.Sprintf("127.0.0.1:%d", port), Handler: http.HandlerFunc(func(w http.ResponseWriter, _ *http.Request) {
		select {
		case entered <- struct{}{}:
		default:
		}
		<-release
	})}
	go srv.ListenAndServe()
	defer srv.Close()
	defer close(release)
	waitListening(t, port)

	ticked := make(chan struct{})
	go func() { s.Tick(time.Now()); close(ticked) }()
	<-entered // the check is now blocked inside the probe
	begin := time.Now()
	_ = s.Snapshot()
	if d := time.Since(begin); d > 200*time.Millisecond {
		t.Fatalf("status waited %v on a running check", d)
	}
	<-ticked
}

func TestControlEndpointAcceptsOnlyLoopbackHosts(t *testing.T) {
	for host, want := range map[string]bool{
		"127.0.0.1:47411": true, "localhost:47411": true, "[::1]:47411": true,
		"127.0.0.1:1": false, "evil.example:47411": false, "10.0.0.5:47411": false,
		"127.0.0.1": false, "": false,
	} {
		if got := localHost(host, "127.0.0.1:47411"); got != want {
			t.Errorf("localHost(%q) = %v, want %v", host, got, want)
		}
	}
	for env, want := range map[string]string{
		"": defaultAddr, ":5000": "127.0.0.1:5000", "0.0.0.0:5000": "127.0.0.1:5000",
		"10.0.0.5:5000": "127.0.0.1:5000", "127.0.0.1:5000": "127.0.0.1:5000", "garbage": defaultAddr,
	} {
		t.Setenv("NOUGEN_SUPERVISOR_ADDR", env)
		if got := addr(); got != want {
			t.Errorf("addr() with %q = %q, want %q", env, got, want)
		}
	}
}

func TestLegacyShellValuesWithQuotesAreReadWhole(t *testing.T) {
	base := t.TempDir()
	dir := filepath.Join(base, "acct")
	os.MkdirAll(filepath.Join(dir, "NouGenShards"), 0o700)
	os.WriteFile(filepath.Join(dir, "NouGenShards", "app.py"), nil, 0o600)
	os.WriteFile(filepath.Join(dir, "run.sh"), []byte(
		`export NGS_NODE_TOKEN='ab'\''cd' NGS_HUD_USER='acct' NGS_PORT='4450'`+"\n"+
			`nohup cloudflared tunnel run --token 'tu'\''nnel' &`+"\n"), 0o600)
	got := Discover(base)
	if len(got) != 1 || got[0].Token != "ab'cd" || got[0].Tunnel != "tu'nnel" {
		t.Fatalf("got %+v", got)
	}
}

func TestSameAccountMatchesOnlyThatFolder(t *testing.T) {
	dir := filepath.Join("C:", "Users", "x", "NouGen", "acct")
	for cmdline, want := range map[string]bool{
		`python.exe ` + filepath.Join(dir, "NouGenShards", "app.py"):      true,
		`python.exe ` + dir + `2` + string(filepath.Separator) + `app.py`: false, // a sibling whose name starts the same
		`some other program`: false,
	} {
		if got := sameAccount(cmdline, dir); got != want {
			t.Errorf("sameAccount(%q) = %v, want %v", cmdline, got, want)
		}
	}
	if sameAccount("anything", "") {
		t.Error("an empty folder matched")
	}
}
