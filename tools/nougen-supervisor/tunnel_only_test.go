package main

import (
	"encoding/json"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
)

// writeTunnelOnly writes a tunnel-only account: node.json with no node, and a
// token file kept outside it, the way the vault tunnel is set up.
func writeTunnelOnly(t *testing.T, base, id string, port int, token string) string {
	t.Helper()
	dir := filepath.Join(base, id)
	if err := os.MkdirAll(dir, 0o700); err != nil {
		t.Fatal(err)
	}
	tokFile := filepath.Join(t.TempDir(), "tunnel.token")
	if err := os.WriteFile(tokFile, []byte(token+"\n"), 0o600); err != nil {
		t.Fatal(err)
	}
	b, _ := json.Marshal(map[string]any{"id": id, "port": port, "tunnel_only": true, "tunnel_file": tokFile})
	if err := os.WriteFile(filepath.Join(dir, "node.json"), b, 0o600); err != nil {
		t.Fatal(err)
	}
	return tokFile
}

func TestTunnelOnlyAccountNeedsNoNodeAndReadsItsTokenFile(t *testing.T) {
	base := t.TempDir()
	writeTunnelOnly(t, base, "vault", freePort(t), "tunnel-token-value")
	nodes := Discover(base)
	if len(nodes) != 1 {
		t.Fatalf("discovered %d accounts, want 1", len(nodes))
	}
	n := nodes[0]
	if !n.TunnelOnly || n.Tunnel != "tunnel-token-value" || n.Token != "" {
		t.Fatalf("got tunnel-only %v, tunnel %q, token %q", n.TunnelOnly, n.Tunnel, n.Token)
	}
}

func TestTunnelOnlyRejectsBadDefinitions(t *testing.T) {
	base := t.TempDir()
	cases := map[string]map[string]any{
		"no tunnel":       {"id": "a", "port": 4501, "tunnel_only": true},
		"relative token":  {"id": "b", "port": 4502, "tunnel_only": true, "tunnel_file": "tunnel.token"},
		"missing token":   {"id": "c", "port": 4503, "tunnel_only": true, "tunnel_file": filepath.Join(base, "nope")},
		"no port":         {"id": "d", "tunnel": "x", "tunnel_only": true},
		"relative binary": {"id": "e", "port": 4505, "tunnel": "x", "tunnel_only": true, "cloudflared": "cloudflared.exe"},
	}
	for name, def := range cases {
		dir := filepath.Join(base, def["id"].(string))
		os.MkdirAll(dir, 0o700)
		b, _ := json.Marshal(def)
		os.WriteFile(filepath.Join(dir, "node.json"), b, 0o600)
		if _, ok := loadNode(dir); ok {
			t.Errorf("%s: accepted, want rejected", name)
		}
	}
}

// countingLauncher records every node start, so a test can prove none happened.
type countingLauncher struct {
	fakeLauncher
	nodeStarts *int
}

func (c countingLauncher) Node(n Node) *exec.Cmd {
	*c.nodeStarts++
	return c.fakeLauncher.Node(n)
}

func TestTunnelOnlyAccountRunsItsTunnelAndNeverANode(t *testing.T) {
	starts := 0
	s, base := newTest(t, countingLauncher{fakeLauncher{node: "ok", tunnel: "ok"}, &starts}, fastTiming())
	writeTunnelOnly(t, base, "vault", freePort(t), "tunnel-token-value")
	tickUntil(t, s, "tunnel up", func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Tunnel.State == "up"
	})
	st := s.Snapshot().Nodes[0]
	if st.Node.State != "none" {
		t.Fatalf("node state %q, want none", st.Node.State)
	}
	if starts != 0 {
		t.Fatalf("started %d nodes for a tunnel-only account, want 0", starts)
	}
}

func TestTunnelOnlyTunnelIsRestartedWhenItDies(t *testing.T) {
	starts := 0
	s, base := newTest(t, countingLauncher{fakeLauncher{node: "ok", tunnel: "ok"}, &starts}, fastTiming())
	writeTunnelOnly(t, base, "vault", freePort(t), "tunnel-token-value")
	up := func() bool {
		st := s.Snapshot()
		return len(st.Nodes) == 1 && st.Nodes[0].Tunnel.State == "up"
	}
	tickUntil(t, s, "first start", up)
	e := s.entries["vault"]
	old := e.tun.proc
	killGroup(old)
	<-old.done
	tickUntil(t, s, "restart", func() bool { return up() && e.tun.proc != old })
	if starts != 0 {
		t.Fatalf("started %d nodes, want 0", starts)
	}
}
