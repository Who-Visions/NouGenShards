package main

// End to end: the Go relay against the UNCHANGED Python node client
// (src/nougen_shards/relay_client.py). If this passes, a node needs no change to
// move from the Worker relay to this one: only its relay_url differs.
//
// The test skips itself when python or the client source is not available.

import (
	"bytes"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

func TestPythonClientAgainstTheGoRelay(t *testing.T) {
	py, err := exec.LookPath("python")
	if err != nil {
		t.Skip("python not on PATH")
	}
	src, _ := filepath.Abs(filepath.Join("..", "src"))
	if _, err := os.Stat(filepath.Join(src, "nougen_shards", "relay_client.py")); err != nil {
		t.Skip("relay_client.py not found next to relay-go")
	}

	// 1. The relay, over TLS (the Python client refuses anything that is not wss/https).
	st := NewMemStore()
	const id = "e2e-node"
	_ = st.Put(id, sha256Hex(testToken))
	relay := httptest.NewTLSServer(NewServer(Config{Timeout: 10 * time.Second}, st))
	defer relay.Close()
	relayURL := "wss://" + strings.TrimPrefix(relay.URL, "https://")

	// 2. The node's own app, on loopback, standing in for NouGen on :4444.
	app := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		b, _ := io.ReadAll(r.Body)
		w.Header().Set("x-from-app", "yes")
		w.Header().Add("set-cookie", "a=1")
		w.Header().Add("set-cookie", "b=2")
		fmt.Fprintf(w, "app saw %s %s body=%q", r.Method, r.URL.RequestURI(), b)
	}))
	defer app.Close()
	appURL, _ := url.Parse(app.URL)

	// 3. node.json and a CA bundle holding the test relay's certificate.
	dir := t.TempDir()
	nodeJSON := filepath.Join(dir, "node.json")
	nj, _ := json.Marshal(map[string]any{"id": id, "token": testToken, "port": mustPort(t, appURL), "relay_url": relayURL})
	if err := os.WriteFile(nodeJSON, nj, 0o600); err != nil {
		t.Fatal(err)
	}
	ca := filepath.Join(dir, "ca.pem")
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: relay.Certificate().Raw})
	if err := os.WriteFile(ca, pemBytes, 0o600); err != nil {
		t.Fatal(err)
	}

	env := append(os.Environ(),
		"PYTHONPATH="+src, "NOUGEN_RELAY_CA_BUNDLE="+ca, "NOUGEN_VAULT_DIR="+filepath.Join(dir, "vault"),
		"NOUGEN_RELAY_HEARTBEAT_S=2",
		"HTTPS_PROXY=", "https_proxy=", "ALL_PROXY=", "all_proxy=", "HTTP_PROXY=", "http_proxy=", "NO_PROXY=*", "no_proxy=*")

	// 4. `probe` is what setup runs before switching a computer to the relay.
	probe := exec.Command(py, "-m", "nougen_shards.relay_client", "probe", "--node-json", nodeJSON)
	probe.Env = env
	if out, err := probe.CombinedOutput(); err != nil {
		t.Fatalf("python probe against the Go relay failed: %v\n%s", err, out)
	}

	// 5. `run` is what the supervisor keeps alive.
	var log bytes.Buffer
	run := exec.Command(py, "-m", "nougen_shards.relay_client", "run", "--node-json", nodeJSON)
	run.Env = env
	run.Stdout, run.Stderr = &log, &log
	if err := run.Start(); err != nil {
		t.Fatal(err)
	}
	defer func() { _ = run.Process.Kill(); _, _ = run.Process.Wait() }()

	client := relay.Client()
	deadline := time.Now().Add(25 * time.Second)
	for {
		req, _ := http.NewRequest("GET", relay.URL+"/_relay/status?id="+id, nil)
		req.Header.Set("Authorization", "Bearer "+testToken)
		if resp, err := client.Do(req); err == nil {
			var m map[string]any
			_ = json.NewDecoder(resp.Body).Decode(&m)
			resp.Body.Close()
			if m["live"] == true {
				break
			}
		}
		if time.Now().After(deadline) {
			t.Fatalf("the Python client never became live on the Go relay.\nclient output:\n%s", log.String())
		}
		time.Sleep(200 * time.Millisecond)
	}

	// 6. A public request goes in the front and comes out of the node's app.
	resp, err := client.Get(relay.URL + "/n/" + id + "/api/x?y=1")
	if err != nil {
		t.Fatal(err)
	}
	b, _ := io.ReadAll(resp.Body)
	resp.Body.Close()
	if resp.StatusCode != 200 || string(b) != `app saw GET /api/x?y=1 body=""` {
		t.Fatalf("GET through the relay: %d %q\nclient output:\n%s", resp.StatusCode, b, log.String())
	}
	if resp.Header.Get("x-nougen-transport") != "relay" || resp.Header.Get("x-from-app") != "yes" {
		t.Errorf("headers: %v", resp.Header)
	}
	if got := resp.Header.Values("set-cookie"); len(got) != 2 {
		t.Errorf("repeated Set-Cookie must survive the round trip, got %v", got)
	}

	resp, err = client.Post(relay.URL+"/n/"+id+"/echo", "application/json", strings.NewReader(`{"k":"v"}`))
	if err != nil {
		t.Fatal(err)
	}
	b, _ = io.ReadAll(resp.Body)
	resp.Body.Close()
	if string(b) != `app saw POST /echo body="{\"k\":\"v\"}"` {
		t.Errorf("POST through the relay: %q", b)
	}
}

func mustPort(t *testing.T, u *url.URL) int {
	t.Helper()
	var p int
	if _, err := fmt.Sscanf(u.Port(), "%d", &p); err != nil {
		t.Fatal(err)
	}
	return p
}
