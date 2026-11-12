//go:build windows

package main

import (
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// writeNode creates <dir>/run.ps1 (+ NouGenShards/ and optional public.txt) like the join setup does.
func writeNode(t *testing.T, dir, runPS1, public string) {
	t.Helper()
	if err := os.MkdirAll(filepath.Join(dir, "NouGenShards"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "run.ps1"), []byte(runPS1), 0o644); err != nil {
		t.Fatal(err)
	}
	if public != "" {
		if err := os.WriteFile(filepath.Join(dir, "public.txt"), []byte(public+"/\n"), 0o644); err != nil {
			t.Fatal(err)
		}
	}
}

const perAccount = "\xef\xbb\xbf$env:NGS_NODE_TOKEN = 'tok-a'\n$env:NGS_PORT = '4445'\n" +
	"$h = Join-Path $env:LOCALAPPDATA 'NouGen'\n$t = Join-Path $h 'alice'\n" +
	"$env:NOUGEN_VAULT_DIR = Join-Path $t 'shards'; $env:NOUGEN_HOME = $t\n" +
	"Start-Process -FilePath (Join-Path $t 'cloudflared.exe') -ArgumentList 'tunnel','--no-autoupdate','run','--token','tun-a'\n"

const legacy = "$env:NGS_NODE_TOKEN = 'tok-root'\n$env:NGS_PORT = '4444'\n" +
	"Start-Process -FilePath (Join-Path $h 'cloudflared.exe') -ArgumentList 'tunnel','--no-autoupdate','run','--token','tun-root'\n"

func TestDiscoverBothLayouts(t *testing.T) {
	home = t.TempDir()
	writeNode(t, home, legacy, "https://root.example")
	writeNode(t, filepath.Join(home, "alice"), perAccount, "https://alice.example")
	if err := os.WriteFile(filepath.Join(home, "alice", "cloudflared.exe"), nil, 0o644); err != nil {
		t.Fatal(err)
	}
	nodes := discover()
	if len(nodes) != 2 {
		t.Fatalf("want 2 nodes, got %d", len(nodes))
	}
	root, alice := nodes[0], nodes[1]
	if root.name != "root" || root.port != 4444 || root.tunnel != "tun-root" || root.public != "https://root.example" {
		t.Errorf("root parsed wrong: %+v", root)
	}
	if _, ok := root.env["NOUGEN_VAULT_DIR"]; ok {
		t.Errorf("legacy node must not get a per-account vault")
	}
	if root.cloudflared != filepath.Join(home, "cloudflared.exe") {
		t.Errorf("root cloudflared = %s", root.cloudflared)
	}
	if alice.name != "alice" || alice.port != 4445 || alice.tunnel != "tun-a" || alice.public != "https://alice.example" {
		t.Errorf("alice parsed wrong: %+v", alice)
	}
	if got, want := alice.env["NOUGEN_VAULT_DIR"], filepath.Join(home, "alice", "shards"); got != want {
		t.Errorf("alice vault = %q, want %q (BOM must be stripped too)", got, want)
	}
	if alice.cloudflared != filepath.Join(home, "alice", "cloudflared.exe") {
		t.Errorf("alice cloudflared = %s", alice.cloudflared)
	}
}

func TestSkipsIncompleteNodes(t *testing.T) {
	home = t.TempDir()
	writeNode(t, filepath.Join(home, "noport"), "$env:NGS_NODE_TOKEN = 'x'\n'--token','t'\n", "")
	writeNode(t, filepath.Join(home, "notunnel"), "$env:NGS_PORT = '4447'\n", "")
	if err := os.MkdirAll(filepath.Join(home, "nocode"), 0o755); err != nil {
		t.Fatal(err)
	}
	_ = os.WriteFile(filepath.Join(home, "nocode", "run.ps1"), []byte(perAccount), 0o644) // no NouGenShards dir
	if n := discover(); len(n) != 0 {
		t.Fatalf("want 0 nodes, got %d: %+v", len(n), n)
	}
}

func TestAliveTracksExit(t *testing.T) {
	p := &proc{done: make(chan struct{})}
	if !alive(p) {
		t.Fatal("open done channel should be alive")
	}
	close(p.done)
	if alive(p) || alive(nil) {
		t.Fatal("closed or nil proc should not be alive")
	}
}

func TestBackoffDoublesAndCaps(t *testing.T) {
	cases := []struct {
		fails int
		want  time.Duration
	}{{-1, time.Minute}, {0, time.Minute}, {1, 2 * time.Minute}, {3, 8 * time.Minute}, {10, 30 * time.Minute}}
	for _, c := range cases {
		if got := backoff(time.Minute, c.fails, 30*time.Minute); got != c.want {
			t.Errorf("backoff(fails=%d) = %v, want %v", c.fails, got, c.want)
		}
	}
}

func TestRefreshKeepsRuntimeAndPicksUpNewNodes(t *testing.T) {
	home = t.TempDir()
	writeNode(t, home, legacy, "https://root.example")
	nodes := refresh(nil)
	if len(nodes) != 1 {
		t.Fatalf("want 1 node, got %d", len(nodes))
	}
	nodes[0].restarts, nodes[0].appFails = 7, 2
	p := &proc{done: make(chan struct{})}
	nodes[0].app = p

	writeNode(t, filepath.Join(home, "alice"), perAccount, "https://alice.example") // new account appears
	if err := os.WriteFile(filepath.Join(home, "public.txt"), []byte("https://moved.example\n"), 0o644); err != nil {
		t.Fatal(err)
	}
	nodes = refresh(nodes)
	if len(nodes) != 2 {
		t.Fatalf("want 2 nodes after refresh, got %d", len(nodes))
	}
	if nodes[0].restarts != 7 || nodes[0].appFails != 2 || nodes[0].app != p {
		t.Errorf("runtime state lost: %+v", nodes[0])
	}
	if nodes[0].public != "https://moved.example" {
		t.Errorf("config not refreshed: public = %q", nodes[0].public)
	}
	if nodes[1].name != "alice" {
		t.Errorf("new node not picked up: %+v", nodes[1])
	}
}

func TestStatusHasNoSecrets(t *testing.T) {
	home = t.TempDir()
	writeNode(t, filepath.Join(home, "alice"), perAccount, "https://alice.example")
	publish(time.Now(), refresh(nil))
	rec := httptest.NewRecorder()
	statusHandler(rec, httptest.NewRequest("GET", "/status", nil))
	body := rec.Body.String()
	if !strings.Contains(body, `"name":"alice"`) || !strings.Contains(body, `"port":4445`) {
		t.Fatalf("status missing node: %s", body)
	}
	for _, secret := range []string{"tok-a", "tun-a", "NGS_NODE_TOKEN"} {
		if strings.Contains(body, secret) {
			t.Errorf("status leaks %q: %s", secret, body)
		}
	}
}
