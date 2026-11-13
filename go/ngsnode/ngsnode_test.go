package main

import (
	"bytes"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"math"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// writeSidecar writes a matrix the way numpy.save + core._save_vector_sidecar do.
func writeSidecar(t *testing.T, vault string, db int, rows [][]float32, ids []int64, dom []string) {
	t.Helper()
	dir := filepath.Join(vault, ".vector-cache")
	if err := os.MkdirAll(dir, 0o755); err != nil {
		t.Fatal(err)
	}
	dim := 0
	if len(rows) > 0 {
		dim = len(rows[0])
	}
	header := fmt.Sprintf("{'descr': '<f4', 'fortran_order': False, 'shape': (%d, %d), }", len(rows), dim)
	for (10+len(header)+1)%64 != 0 {
		header += " "
	}
	header += "\n"
	var buf bytes.Buffer
	buf.WriteString("\x93NUMPY\x01\x00")
	_ = binary.Write(&buf, binary.LittleEndian, uint16(len(header)))
	buf.WriteString(header)
	for _, r := range rows {
		_ = binary.Write(&buf, binary.LittleEndian, r)
	}
	base := filepath.Join(dir, fmt.Sprintf("db%d-%016x", db, db))
	if err := os.WriteFile(base+".npy", buf.Bytes(), 0o644); err != nil {
		t.Fatal(err)
	}
	meta, _ := json.Marshal(map[string]interface{}{"v": 2, "dim": dim, "sha256": "x", "ids": ids, "dom": dom})
	if err := os.WriteFile(base+".json", meta, 0o644); err != nil {
		t.Fatal(err)
	}
}

func unit(v ...float32) []float32 {
	var n float64
	for _, x := range v {
		n += float64(x * x)
	}
	out := make([]float32, len(v))
	for i, x := range v {
		out[i] = float32(float64(x) / math.Sqrt(n))
	}
	return out
}

func testIndex(t *testing.T) *vectorIndex {
	t.Helper()
	vault := t.TempDir()
	writeSidecar(t, vault, 1,
		[][]float32{unit(1, 0, 0, 0, 0), unit(0, 1, 0, 0, 0), unit(1, 1, 0, 0, 0)},
		[]int64{10, 11, 12}, []string{"global", "ops", "global"})
	writeSidecar(t, vault, 2,
		[][]float32{unit(1, 0.1, 0, 0, 0), unit(0, 0, 1, 0, 0)},
		[]int64{20, 21}, []string{"ops", "global"})
	ix := newVectorIndex(vault)
	if errs := ix.refresh(); len(errs) > 0 {
		t.Fatal(errs)
	}
	return ix
}

func TestSearchRanksAcrossDBs(t *testing.T) {
	ix := testIndex(t)
	res := ix.search(unit(1, 0, 0, 0, 0), 3, "*")
	if res.Rows != 5 || len(res.DBs) != 2 {
		t.Fatalf("rows=%d dbs=%v", res.Rows, res.DBs)
	}
	got := fmt.Sprint(res.Hits[0].ID, res.Hits[1].ID, res.Hits[2].ID)
	if got != "10 20 12" {
		t.Fatalf("order = %s, want 10 20 12", got)
	}
	if math.Abs(float64(res.Hits[0].Score)-1) > 1e-6 {
		t.Fatalf("top score = %v, want 1", res.Hits[0].Score)
	}
}

func TestSearchDomainFilter(t *testing.T) {
	ix := testIndex(t)
	res := ix.search(unit(1, 0, 0, 0, 0), 10, "ops")
	if len(res.Hits) != 2 || res.Hits[0].ID != 20 || res.Hits[1].ID != 11 {
		t.Fatalf("hits = %+v", res.Hits)
	}
}

func TestSearchSkipsOtherDims(t *testing.T) {
	ix := testIndex(t)
	res := ix.search([]float32{1, 0, 0}, 10, "")
	if len(res.Hits) != 0 || len(res.Skipped) != 2 {
		t.Fatalf("hits=%v skipped=%v", res.Hits, res.Skipped)
	}
}

func TestRefreshPicksUpRewriteAndRejectsMismatch(t *testing.T) {
	vault := t.TempDir()
	writeSidecar(t, vault, 1, [][]float32{unit(1, 0)}, []int64{1}, []string{"g"})
	ix := newVectorIndex(vault)
	ix.refresh()
	// A pair caught mid-swap (matrix has 2 rows, metadata still 1) is refused
	// and the previous mapping keeps serving.
	base := filepath.Join(vault, ".vector-cache", fmt.Sprintf("db%d-%016x", 1, 1))
	oldMeta, _ := os.ReadFile(base + ".json")
	writeSidecar(t, vault, 1, [][]float32{unit(1, 0), unit(0, 1)}, []int64{1, 2}, []string{"g", "g"})
	newMeta, _ := os.ReadFile(base + ".json")
	_ = os.WriteFile(base+".json", oldMeta, 0o644)
	if errs := ix.refresh(); len(errs) != 1 {
		t.Fatalf("want 1 mismatch error, got %v", errs)
	}
	if st := ix.status(); len(st) != 1 || st[0].Rows != 1 {
		t.Fatalf("status after mismatch = %+v", st)
	}
	_ = os.WriteFile(base+".json", newMeta, 0o644)
	if errs := ix.refresh(); len(errs) != 0 {
		t.Fatal(errs)
	}
	if st := ix.status(); st[0].Rows != 2 {
		t.Fatalf("rows after rewrite = %d", st[0].Rows)
	}
}

func TestParseNpyHeaderRejectsWrongDtype(t *testing.T) {
	h := "{'descr': '<f8', 'fortran_order': False, 'shape': (1, 2), }\n"
	b := append([]byte("\x93NUMPY\x01\x00"), byte(len(h)), 0)
	b = append(b, h...)
	b = append(b, make([]byte, 16)...)
	if _, _, _, err := parseNpyHeader(b); err == nil {
		t.Fatal("float64 matrix accepted")
	}
}

func TestHTTPAuthSearchAndProxy(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fmt.Fprintf(w, "py:%s:%s:%s", r.URL.Path, r.Host, r.Header.Get("X-NGS-Token"))
	}))
	defer backend.Close()
	u, _ := url.Parse(backend.URL)
	n := &node{token: "s3cret", index: testIndex(t), proxy: newProxy(u)}
	front := httptest.NewServer(n.routes())
	defer front.Close()

	do := func(method, path, token, body string) (int, string) {
		req, _ := http.NewRequest(method, front.URL+path, strings.NewReader(body))
		if token != "" {
			req.Header.Set("X-NGS-Token", token)
		}
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			t.Fatal(err)
		}
		defer resp.Body.Close()
		var b bytes.Buffer
		_, _ = b.ReadFrom(resp.Body)
		return resp.StatusCode, b.String()
	}

	if code, _ := do("POST", "/v1/vector/search", "", `{"embedding":[1,0,0,0,0]}`); code != 401 {
		t.Fatalf("no token: %d, want 401", code)
	}
	if code, _ := do("POST", "/v1/vector/search", "wrong", `{"embedding":[1,0,0,0,0]}`); code != 401 {
		t.Fatalf("wrong token: %d, want 401", code)
	}
	code, body := do("POST", "/v1/vector/search", "s3cret", `{"embedding":[1,0,0,0,0],"top_n":1}`)
	if code != 200 || !strings.Contains(body, `"id":10`) {
		t.Fatalf("search: %d %s", code, body)
	}
	if code, _ := do("GET", "/v1/vector/search", "s3cret", ""); code != 405 {
		t.Fatalf("GET search: %d, want 405", code)
	}
	if code, body := do("GET", "/livez", "", ""); code != 200 || !strings.Contains(body, `"front":"go"`) {
		t.Fatalf("livez: %d %s", code, body)
	}
	// Unported routes reach the worker with the path, Host and token intact.
	code, body = do("GET", "/search?q=x", "s3cret", "")
	want := "py:/search:" + strings.TrimPrefix(front.URL, "http://") + ":s3cret"
	if code != 200 || body != want {
		t.Fatalf("proxy: %d %q, want %q", code, body, want)
	}

	// No token configured: data routes refuse, as the Python app does.
	n2 := &node{index: testIndex(t)}
	rec := httptest.NewRecorder()
	n2.routes().ServeHTTP(rec, httptest.NewRequest("GET", "/v1/vector/status", nil))
	if rec.Code != 503 {
		t.Fatalf("unconfigured token: %d, want 503", rec.Code)
	}
}

func TestProxyWorkerDownIs502(t *testing.T) {
	u, _ := url.Parse("http://127.0.0.1:1")
	n := &node{token: "t", index: newVectorIndex(t.TempDir()), proxy: newProxy(u)}
	rec := httptest.NewRecorder()
	n.routes().ServeHTTP(rec, httptest.NewRequest("GET", "/health", nil))
	if rec.Code != 502 {
		t.Fatalf("worker down: %d, want 502", rec.Code)
	}
}
