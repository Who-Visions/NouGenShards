package main

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"database/sql"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"strconv"
	"strings"
	"testing"
	"time"
)

var testNow = time.Date(2026, 11, 13, 0, 0, 0, 0, time.UTC)

const testNowRFC = "2026-11-13T00:00:00Z"

func blob(v []float32) []byte {
	var b bytes.Buffer
	_ = binary.Write(&b, binary.LittleEndian, v)
	return b.Bytes()
}

type testRow struct {
	id   int64
	ts   string
	util float64
	dom  string
	typ  string
	emb  []byte
}

// grid is one SQLite DB plus the sidecar saved from its first `saved` rows.
type grid struct {
	t     *testing.T
	vault string
	path  string
	db    *sql.DB
	clock int64
}

func newGrid(t *testing.T, rows []testRow, saved int) (*grid, *vectorIndex) {
	t.Helper()
	vault := t.TempDir()
	g := &grid{t: t, vault: vault, path: filepath.Join(vault, "nougen_shards_1.db"), clock: 1_800_000_000}
	db, err := sql.Open("sqlite", g.path)
	if err != nil {
		t.Fatal(err)
	}
	t.Cleanup(func() { db.Close() })
	g.db = db
	g.exec(`CREATE TABLE shards (id INTEGER PRIMARY KEY, timestamp TEXT, utility_score REAL,
		domain_key TEXT, event_type TEXT, embedding BLOB)`)
	for _, r := range rows {
		g.insert(r)
	}
	// The sidecar, as core._save_vector_sidecar writes it.
	var vecs [][]float32
	var ids []int64
	var ts, dom, etype []string
	var util []float64
	legacy := [][]interface{}{}
	var maxID int64
	for _, r := range rows[:saved] {
		maxID = r.id
		if len(r.emb) == 8*4 && r.emb[0] != '[' {
			v := make([]float32, 8)
			_ = binary.Read(bytes.NewReader(r.emb), binary.LittleEndian, v)
			vecs, ids, ts, dom = append(vecs, v), append(ids, r.id), append(ts, r.ts), append(dom, r.dom)
			etype, util = append(etype, strings.ToUpper(r.typ)), append(util, r.util)
		} else {
			legacy = append(legacy, []interface{}{r.id, r.util, r.ts, r.dom, strings.ToUpper(r.typ),
				map[string]string{"hex": hex.EncodeToString(r.emb)}})
		}
	}
	writeSidecar(t, vault, 1, vecs, ids, dom)
	base := filepath.Join(vault, ".vector-cache", fmt.Sprintf("db%d-%016x", 1, 1))
	meta, _ := json.Marshal(map[string]interface{}{"v": 2, "dim": 8, "sha256": "x", "path": g.path,
		"max_id": maxID, "n_embedded": saved, "ids": ids, "ts": ts, "util": util, "dom": dom,
		"etype": etype, "legacy": legacy})
	if err := os.WriteFile(base+".json", meta, 0o644); err != nil {
		t.Fatal(err)
	}
	retrieveStates.Lock()
	delete(retrieveStates.byDB, 1)
	retrieveStates.Unlock()
	ix := newVectorIndex(vault)
	if errs := ix.refresh(); len(errs) > 0 {
		t.Fatal(errs)
	}
	return g, ix
}

func (g *grid) exec(q string, args ...interface{}) {
	g.t.Helper()
	if _, err := g.db.Exec(q, args...); err != nil {
		g.t.Fatal(err)
	}
	// The staleness key is whole-second mtime plus size: make every write visible.
	g.clock += 10
	_ = os.Chtimes(g.path, time.Unix(g.clock, 0), time.Unix(g.clock, 0))
}

func (g *grid) insert(r testRow) {
	g.exec("INSERT INTO shards VALUES (?, ?, ?, ?, ?, ?)", r.id, r.ts, r.util, r.dom, r.typ, r.emb)
}

func axis(i int, scale float32) []byte {
	v := make([]float32, 8)
	v[i] = scale
	return blob(v)
}

func query() []float32 { return []float32{1, 0, 0, 0, 0, 0, 0, 0} }

func idsOf(rows []scoredRow) string {
	var s []string
	for _, r := range rows {
		s = append(s, strconv.FormatInt(r.ID, 10))
	}
	return strings.Join(s, " ")
}

func baseRows() []testRow {
	return []testRow{
		{1, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", axis(0, 1.0)},   // sem 1.0, fresh
		{2, "2026-11-13T00:00:00Z", 1.0, "ops", "knowledge", axis(0, 0.9)},      // sem 0.9
		{3, "2026-10-14T00:00:00Z", 1.0, "global", "bulk_ingest", axis(0, 0.8)}, // sem 0.8, 30 days old
		{4, "2026-11-13T00:00:00Z", 0.0, "global", "knowledge", axis(1, 1.0)},   // sem 0
	}
}

func TestRetrieveScoresLikePython(t *testing.T) {
	_, ix := newGrid(t, baseRows(), 4)
	res := ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, DomainKey: "*", Now: testNowRFC})
	if got := idsOf(res.Rows); got != "1 2 3 4" {
		t.Fatalf("order = %s", got)
	}
	want := []float64{1.0*0.7 + 1.0*1.0*0.3, float64(float32(0.9))*0.7 + 0.3, float64(float32(0.8))*0.7 + 0.5*0.3, 0}
	for i, w := range want {
		if math.Abs(res.Rows[i].FinalScore-w) > 1e-9 {
			t.Fatalf("row %d score = %v, want %v", i, res.Rows[i].FinalScore, w)
		}
	}
	if len(res.DBs) != 1 || len(res.Fallback) != 0 {
		t.Fatalf("dbs=%v fallback=%v", res.DBs, res.Fallback)
	}
}

func TestRetrieveFilters(t *testing.T) {
	_, ix := newGrid(t, baseRows(), 4)
	res := ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, DomainKey: "global", Now: testNowRFC})
	if got := idsOf(res.Rows); got != "1 3 4" {
		t.Fatalf("domain filter: %s", got)
	}
	res = ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, ExcludedTypes: []string{"BULK_INGEST"}, Now: testNowRFC})
	if got := idsOf(res.Rows); got != "1 2 4" {
		t.Fatalf("type filter: %s", got)
	}
	res = ix.retrieve(retrieveRequest{Embedding: query(), Limit: 2, Now: testNowRFC})
	if got := idsOf(res.Rows); got != "1 2" {
		t.Fatalf("limit: %s", got)
	}
}

func TestRetrieveSeesRowsWrittenAfterTheSave(t *testing.T) {
	rows := baseRows()
	g, ix := newGrid(t, rows, 4)
	req := retrieveRequest{Embedding: query(), Limit: 10, Now: testNowRFC}
	ix.retrieve(req)
	g.insert(testRow{5, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", axis(0, 0.95)})
	if got := idsOf(ix.retrieve(req).Rows); got != "1 5 2 3 4" {
		t.Fatalf("after append: %s", got)
	}
	g.exec("DELETE FROM shards WHERE id = 5") // the canary's write-then-delete
	if got := idsOf(ix.retrieve(req).Rows); got != "1 2 3 4" {
		t.Fatalf("after tail delete: %s", got)
	}
	g.exec("DELETE FROM shards WHERE id = 2") // a saved row
	res := ix.retrieve(req)
	if got := idsOf(res.Rows); got != "1 3 4" || len(res.Fallback) != 0 {
		t.Fatalf("after base delete: %s fallback=%v", got, res.Fallback)
	}
}

func TestRetrieveHandsBackABackfilledDB(t *testing.T) {
	rows := append(baseRows(), testRow{9, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", axis(0, 0.5)})
	g, ix := newGrid(t, rows, 5)
	// An old id gains an embedding: at or below max_id, so no tail read can see it.
	g.insert(testRow{6, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", axis(0, 0.99)})
	res := ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, Now: testNowRFC})
	if len(res.Fallback) != 1 || len(res.Rows) != 0 || len(res.DBs) != 0 {
		t.Fatalf("want DB 1 handed back, got rows=%s dbs=%v fallback=%v", idsOf(res.Rows), res.DBs, res.Fallback)
	}
}

func TestRetrieveLegacyAndOddRows(t *testing.T) {
	rows := append(baseRows(),
		testRow{5, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", []byte("[0.5,0,0,0,0,0,0,0]")}, // JSON text, saved
		testRow{6, "", 1.0, "global", "knowledge", blob([]float32{1, 0, 0})},                          // other width, saved
	)
	g, ix := newGrid(t, rows, 6)
	g.insert(testRow{7, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", []byte("[0.7,0,0,0,0,0,0,0]")}) // JSON text, tail
	res := ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, Now: testNowRFC})
	if got := idsOf(res.Rows); got != "1 2 7 3 5 6 4" {
		t.Fatalf("order = %s", got)
	}
	byID := map[int64]float64{}
	for _, r := range res.Rows {
		byID[r.ID] = r.FinalScore
	}
	if math.Abs(byID[5]-(0.5*0.7+0.3)) > 1e-6 || math.Abs(byID[6]-0.3) > 1e-9 || math.Abs(byID[7]-(float64(float32(0.7))*0.7+0.3)) > 1e-6 {
		t.Fatalf("legacy scores: %v", byID)
	}
}

func TestRetrieveDimMismatchIsSkipped(t *testing.T) {
	_, ix := newGrid(t, baseRows(), 4)
	res := ix.retrieve(retrieveRequest{Embedding: []float32{1, 0, 0}, Limit: 10, Now: testNowRFC})
	if len(res.Skipped) != 1 || len(res.Rows) != 0 {
		t.Fatalf("skipped=%v rows=%s", res.Skipped, idsOf(res.Rows))
	}
}

func TestRetrieveMissingDBIsHandedBack(t *testing.T) {
	g, ix := newGrid(t, baseRows(), 4)
	g.db.Close()
	if err := os.Remove(g.path); err != nil {
		t.Fatal(err)
	}
	res := ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, Now: testNowRFC})
	if len(res.Fallback) != 1 || len(res.Rows) != 0 {
		t.Fatalf("fallback=%v rows=%s", res.Fallback, idsOf(res.Rows))
	}
}

func TestTemporalDecay(t *testing.T) {
	half := 0.5
	cases := []struct {
		ts   string
		want float64
	}{
		{"", 1.0},
		{"2026-10-14T00:00:00Z", half},
		{"2026-10-14T00:00:00.000000Z", half},
		{"2026-10-14T00:00:00.000Z", half},
		{"2026-10-14 00:00:00", half},
		{"2026-10-14T00:00:00", half},
		{"2026-10-14T00:00:00.000000", half},
		{"2026-10-14T00:00:00+00:00", half},
		{"2026-10-13T20:00:00-04:00", half},
		{"2026-10-13T20:00:00-0400", half},
		{"2026-10-14", half},
		{"2026-10-14T00:00", half},
		{"2026-11-13T00:00:00Z", 1.0},
		{"2020-01-01T00:00:00Z", 0.1},   // floored
		{"2026-09-12 12:49:23 AM", 1.0}, // Python cannot parse this either
		{"yesterday", 1.0},
		{"2026-13-45T00:00:00Z", 1.0},
	}
	for _, c := range cases {
		if got := temporalDecay(c.ts, testNow); math.Abs(got-c.want) > 1e-12 {
			t.Errorf("temporalDecay(%q) = %v, want %v", c.ts, got, c.want)
		}
	}
}

// TestDecayMatchesPython checks temporalDecay against values computed by
// core._temporal_decay for real vault timestamps. Opt-in: set
// NGS_DECAY_FIXTURE to a TSV of "<now RFC3339>" on line 1, then "ts\tdecay".
func TestDecayMatchesPython(t *testing.T) {
	path := os.Getenv("NGS_DECAY_FIXTURE")
	if path == "" {
		t.Skip("NGS_DECAY_FIXTURE not set")
	}
	f, err := os.Open(path)
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 1<<20), 1<<20)
	sc.Scan()
	now, err := time.Parse(time.RFC3339Nano, sc.Text())
	if err != nil {
		t.Fatal(err)
	}
	n, bad := 0, 0
	for sc.Scan() {
		parts := strings.SplitN(sc.Text(), "\t", 2)
		want, _ := strconv.ParseFloat(parts[1], 64)
		n++
		if got := temporalDecay(parts[0], now); math.Abs(got-want) > 1e-9 {
			if bad++; bad <= 10 {
				t.Errorf("temporalDecay(%q) = %v, Python says %v", parts[0], got, want)
			}
		}
	}
	t.Logf("%d timestamps compared, %d differ", n, bad)
}

func TestSaveFoldsTheTailIntoTheSidecar(t *testing.T) {
	old := sidecarResaveRows
	sidecarResaveRows = 2
	defer func() { sidecarResaveRows = old }()
	rows := append(baseRows(), testRow{5, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", []byte("[0.5,0,0,0,0,0,0,0]")})
	g, ix := newGrid(t, rows, 5)
	req := retrieveRequest{Embedding: query(), Limit: 10, Now: testNowRFC}
	g.exec("DELETE FROM shards WHERE id = 2") // a saved row goes
	g.insert(testRow{6, "2026-11-13T00:00:00Z", 1.0, "ops", "note", axis(0, 0.95)})
	before := ix.retrieve(req) // one tail row: below the threshold, nothing written
	base := filepath.Join(g.vault, ".vector-cache", fmt.Sprintf("db%d-%016x", 1, 1))
	if st, _ := os.Stat(base + ".npy"); st.Size() != 128+4*8*4 {
		t.Fatalf("saved too early: %d bytes", st.Size())
	}
	g.insert(testRow{7, "", 0.5, "global", "knowledge", axis(0, 0.6)})
	g.insert(testRow{8, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", []byte("[0.7,0,0,0,0,0,0,0]")}) // legacy, tail
	want := ix.retrieve(req)                                                                                // tail is now 2 vectors + 1 legacy: saved after scoring
	if got := idsOf(want.Rows); got != "1 6 8 3 5 7 4" {
		t.Fatalf("order before reload = %s (first pass %s)", got, idsOf(before.Rows))
	}
	var meta struct {
		V         int                 `json:"v"`
		Path      string              `json:"path"`
		Dim       int                 `json:"dim"`
		NEmbedded int                 `json:"n_embedded"`
		MaxID     int64               `json:"max_id"`
		SHA256    string              `json:"sha256"`
		IDs       []int64             `json:"ids"`
		Util      []float64           `json:"util"`
		EType     []string            `json:"etype"`
		Legacy    [][]json.RawMessage `json:"legacy"`
	}
	raw, _ := os.ReadFile(base + ".json")
	if err := json.Unmarshal(raw, &meta); err != nil {
		t.Fatal(err)
	}
	if fmt.Sprint(meta.IDs) != "[1 3 4 6 7]" || meta.MaxID != 8 || meta.NEmbedded != 7 || meta.V != 2 ||
		meta.Dim != 8 || meta.Path != g.path || len(meta.Legacy) != 2 || meta.EType[3] != "NOTE" {
		t.Fatalf("metadata = %+v", meta)
	}
	npy, _ := os.ReadFile(base + ".npy")
	off, n, dim, err := parseNpyHeader(npy)
	if err != nil || n != 5 || dim != 8 || off%64 != 0 {
		t.Fatalf("npy header: off=%d rows=%d dim=%d err=%v", off, n, dim, err)
	}
	if sum := sha256.Sum256(npy[off:]); hex.EncodeToString(sum[:]) != meta.SHA256 {
		t.Fatal("sha256 in the metadata is not the matrix's")
	}
	if _, err := os.Stat(base + ".npy.lock"); !os.IsNotExist(err) {
		t.Fatal("save lock left behind")
	}
	// The next refresh maps the new pair; the tail is empty and ranking is unchanged.
	if errs := ix.refresh(); len(errs) > 0 {
		t.Fatal(errs)
	}
	after := ix.retrieve(req)
	if idsOf(after.Rows) != idsOf(want.Rows) || len(after.Fallback) != 0 {
		t.Fatalf("after reload = %s fallback=%v", idsOf(after.Rows), after.Fallback)
	}
	for i := range want.Rows {
		if math.Abs(after.Rows[i].FinalScore-want.Rows[i].FinalScore) > 1e-12 {
			t.Fatalf("score of %d changed across the save", want.Rows[i].ID)
		}
	}
	if st := stateFor(1); len(st.tail.ids)+len(st.tail.legacy) != 0 || st.nDead != 0 {
		t.Fatalf("tail=%d legacy=%d dead=%d after reload", len(st.tail.ids), len(st.tail.legacy), st.nDead)
	}
}

func TestSaveSkipsWhenAnotherWriterHoldsTheLock(t *testing.T) {
	old := sidecarResaveRows
	sidecarResaveRows = 1
	defer func() { sidecarResaveRows = old }()
	g, ix := newGrid(t, baseRows(), 4)
	base := filepath.Join(g.vault, ".vector-cache", fmt.Sprintf("db%d-%016x", 1, 1))
	if err := os.WriteFile(base+".npy.lock", []byte("999"), 0o644); err != nil {
		t.Fatal(err)
	}
	g.insert(testRow{5, "2026-11-13T00:00:00Z", 1.0, "global", "knowledge", axis(0, 0.95)})
	res := ix.retrieve(retrieveRequest{Embedding: query(), Limit: 10, Now: testNowRFC})
	if got := idsOf(res.Rows); got != "1 5 2 3 4" {
		t.Fatalf("order = %s", got)
	}
	if st, _ := os.Stat(base + ".npy"); st.Size() != 128+4*8*4 {
		t.Fatal("wrote under another writer's lock")
	}
	if _, err := os.Stat(base + ".npy.lock"); err != nil {
		t.Fatal("removed another writer's lock")
	}
}
