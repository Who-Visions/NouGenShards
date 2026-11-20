package main

import (
	"crypto/sha256"
	"encoding/base64"
	"io"
	"net/http"
	"net/http/httptest"
	"regexp"
	"strings"
	"testing"
)

func fetchPage(t *testing.T, ts *httptest.Server, method, path, host string) (*http.Response, string) {
	t.Helper()
	req, err := http.NewRequest(method, ts.URL+path, nil)
	if err != nil {
		t.Fatal(err)
	}
	if host != "" {
		req.Host = host
	}
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		t.Fatal(err)
	}
	defer resp.Body.Close()
	b, _ := io.ReadAll(resp.Body)
	return resp, string(b)
}

func TestFrontPageServedAtRoot(t *testing.T) {
	ts, _, _ := newRelay(t, Config{HostSuffix: ".relay.test"})
	resp, body := fetchPage(t, ts, "GET", "/", "")
	if resp.StatusCode != 200 {
		t.Fatalf("GET /: %d", resp.StatusCode)
	}
	if ct := resp.Header.Get("content-type"); !strings.HasPrefix(ct, "text/html") {
		t.Fatalf("content-type %q", ct)
	}
	if resp.Header.Get("x-content-type-options") != "nosniff" {
		t.Fatal("missing nosniff")
	}
	csp := resp.Header.Get("content-security-policy")
	for _, want := range []string{"default-src 'self'", "script-src 'none'", "frame-ancestors 'none'", "style-src 'sha256-"} {
		if !strings.Contains(csp, want) {
			t.Fatalf("CSP %q lacks %q", csp, want)
		}
	}
	if resp.Header.Get("cache-control") == "" {
		t.Fatal("missing cache-control")
	}
	if !strings.Contains(body, "NouGen Relay") {
		t.Fatal("page body missing")
	}
}

func TestFrontPageCSPPinsTheInlineStyle(t *testing.T) {
	m := regexp.MustCompile(`(?s)<style>(.*?)</style>`).FindSubmatch(indexHTML)
	if m == nil {
		t.Fatal("no <style> block")
	}
	sum := sha256.Sum256(m[1])
	want := "style-src 'sha256-" + base64.StdEncoding.EncodeToString(sum[:]) + "'"
	if !strings.Contains(frontPageCSP, want) {
		t.Fatalf("CSP does not pin the style block: %s", frontPageCSP)
	}
	if n := strings.Count(string(indexHTML), "<style"); n != 1 {
		t.Fatalf("exactly one style block expected, got %d", n)
	}
}

// The page must obey its own policy: no script, no inline style attributes, no remote loads.
func TestFrontPageObeysItsOwnPolicy(t *testing.T) {
	page := string(indexHTML)
	for _, banned := range []string{"<script", "javascript:", " style=", "onclick=", "onerror=", "<iframe", "<form", "@import", "url(http", "src=\"http"} {
		if strings.Contains(strings.ToLower(page), banned) {
			t.Fatalf("page contains %q", banned)
		}
	}
	// Only same-origin navigation plus the two documentation links on GitHub.
	for _, m := range regexp.MustCompile(`(?:href|src)="([^"]+)"`).FindAllStringSubmatch(page, -1) {
		u := m[1]
		if strings.HasPrefix(u, "#") || u == "/" || strings.HasPrefix(u, "data:") || strings.HasPrefix(u, "https://github.com/Who-Visions/NouGenShards/") {
			continue
		}
		t.Fatalf("unexpected link target %q", u)
	}
}

// Public means public: nothing on the page may describe a live node or the running build.
func TestFrontPageStatesNoLiveFacts(t *testing.T) {
	page := strings.ToLower(string(indexHTML))
	for _, banned := range []string{"nodes online", "online now", "connected nodes", "uptime", "latency", "nominal", "version", "v1."} {
		if strings.Contains(page, banned) {
			t.Fatalf("page makes a live or unbacked claim: %q", banned)
		}
	}
}

// Every limit the page prints must be the real default, not a number that can drift.
func TestFrontPageLimitsMatchDefaults(t *testing.T) {
	page := string(indexHTML)
	if defaultMaxBody != 8<<20 || !strings.Contains(page, "<b>8 MiB</b>") {
		t.Fatalf("body cap on page does not match defaultMaxBody=%d", defaultMaxBody)
	}
	if int(defaultTimeout.Seconds()) != 30 || !strings.Contains(page, "<b>30 s</b>") {
		t.Fatalf("timeout on page does not match defaultTimeout=%v", defaultTimeout)
	}
	cfg := Config{}.withDefaults()
	if int(cfg.IdleTimeout.Seconds()) != 90 || !strings.Contains(page, "<b>90 s</b>") {
		t.Fatalf("idle drop on page does not match IdleTimeout=%v", cfg.IdleTimeout)
	}
	if !strings.Contains(page, "<b>20 s</b>") {
		t.Fatal("heartbeat interval missing from page")
	}
}

func TestFrontPageHeadHasNoBody(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	resp, body := fetchPage(t, ts, "HEAD", "/", "")
	if resp.StatusCode != 200 || body != "" {
		t.Fatalf("HEAD /: %d, %d body bytes", resp.StatusCode, len(body))
	}
	if resp.Header.Get("content-length") == "" {
		t.Fatal("HEAD should still report content-length")
	}
}

func TestFrontPageOnlyAtExactRoot(t *testing.T) {
	ts, _, _ := newRelay(t, Config{})
	for _, p := range []string{"/index.html", "/x", "/favicon.ico", "//"} {
		resp, body := fetchPage(t, ts, "GET", p, "")
		if resp.StatusCode != 404 {
			t.Fatalf("GET %s: %d, want 404", p, resp.StatusCode)
		}
		if strings.Contains(body, "NouGen Relay") {
			t.Fatalf("GET %s served the page", p)
		}
	}
	// Only GET and HEAD.
	resp, _ := fetchPage(t, ts, "POST", "/", "")
	if resp.StatusCode != 404 {
		t.Fatalf("POST /: %d, want 404", resp.StatusCode)
	}
}

func TestFrontPageNeverBecomesANodeRoute(t *testing.T) {
	ts, _, _ := newRelay(t, Config{HostSuffix: ".relay.test"})

	// A host under the suffix that is not a valid node id still gets the page.
	resp, body := fetchPage(t, ts, "GET", "/", "not_a_valid_id!.relay.test")
	if resp.StatusCode != 200 || !strings.Contains(body, "NouGen Relay") {
		t.Fatalf("invalid-id host: %d", resp.StatusCode)
	}
	// The bare suffix host is not a node either.
	resp, body = fetchPage(t, ts, "GET", "/", "relay.test")
	if resp.StatusCode != 200 || !strings.Contains(body, "NouGen Relay") {
		t.Fatalf("bare host: %d", resp.StatusCode)
	}

	// A valid node id under the suffix still routes to the node (offline here), never to the page.
	resp, body = fetchPage(t, ts, "GET", "/", "n1.relay.test")
	if resp.StatusCode != http.StatusBadGateway || strings.Contains(body, "Reach your node") {
		t.Fatalf("n1.relay.test must proxy (offline 502), got %d", resp.StatusCode)
	}
	// So does the path form.
	resp, body = fetchPage(t, ts, "GET", "/n/n1/", "")
	if resp.StatusCode != http.StatusBadGateway || strings.Contains(body, "Reach your node") {
		t.Fatalf("/n/n1/ must proxy (offline 502), got %d", resp.StatusCode)
	}
	// Relay control paths are untouched.
	resp, body = fetchPage(t, ts, "GET", "/_relay/health", "")
	if resp.StatusCode != 200 || body != "ok" {
		t.Fatalf("health: %d %q", resp.StatusCode, body)
	}
	resp, _ = fetchPage(t, ts, "GET", "/_relay/status?id=n1", "")
	if resp.StatusCode != http.StatusUnauthorized {
		t.Fatalf("status without a token: %d, want 401", resp.StatusCode)
	}
}
