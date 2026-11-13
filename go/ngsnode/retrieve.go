package main

// The recall vector lane: the scoring half of Python core._vector_retrieve.
//
// search (vector.go) ranks by cosine over the saved matrices only. retrieve
// is what recall needs: it also covers rows written since a matrix was saved
// (read from SQLite), drops rows deleted since, and ranks by the same blend
// of similarity and time-decayed utility as the Python lane. The caller gets
// (db, id, final_score) and hydrates those rows itself.
//
// A DB this file cannot answer exactly is never guessed at: it is listed in
// Fallback and the caller scores that DB in-process.

import (
	"container/heap"
	"database/sql"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"math"
	"net/http"
	"net/url"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite"
)

const (
	weightLikelihood = 0.7 // core.WEIGHT_LIKELIHOOD
	weightPrior      = 0.3 // core.WEIGHT_PRIOR
)

type retrieveRequest struct {
	Embedding     []float32 `json:"embedding"`
	Limit         int       `json:"limit"`
	DomainKey     string    `json:"domain_key"`     // "" or "*": every domain
	ExcludedTypes []string  `json:"excluded_types"` // upper-case event types to skip
	Now           string    `json:"now"`            // RFC 3339 clock, for tests
}

type scoredRow struct {
	DB         int     `json:"db"`
	ID         int64   `json:"id"`
	FinalScore float64 `json:"final_score"`
}

type retrieveResult struct {
	Rows     []scoredRow `json:"rows"`
	DBs      []int       `json:"dbs"`
	Fallback []int       `json:"fallback"`
	Skipped  []int       `json:"skipped_dim_mismatch"`
	// Paths names the SQLite file each DB index was answered from, so a
	// caller serving several vaults can tell this is the vault it meant.
	Paths map[string]string `json:"paths"`
}

// legacyRow is an embedded row that is not a float32 vector of the DB's
// width (JSON text, or another model's width). Scored one by one.
type legacyRow struct {
	id   int64
	util float64
	ts   string
	dom  string
	typ  string
	emb  []byte
}

// retrieveMeta is the part of a sidecar's JSON that search does not need.
type retrieveMeta struct {
	ts     []string
	util   []float32
	etype  []string
	path   string
	maxID  int64
	legacy []legacyRow
}

type sidecarRetrieveJSON struct {
	Path   string              `json:"path"`
	MaxID  int64               `json:"max_id"`
	TS     []*string           `json:"ts"`
	Util   []float32           `json:"util"`
	EType  []string            `json:"etype"`
	Legacy [][]json.RawMessage `json:"legacy"`
}

func loadRetrieveMeta(metaPath string, rows int) (*retrieveMeta, error) {
	raw, err := os.ReadFile(metaPath)
	if err != nil {
		return nil, err
	}
	var j sidecarRetrieveJSON
	if err := json.Unmarshal(raw, &j); err != nil {
		return nil, fmt.Errorf("%s: %w", metaPath, err)
	}
	if len(j.TS) != rows || len(j.Util) != rows || len(j.EType) != rows {
		return nil, fmt.Errorf("%s: ts/util/etype lengths do not match %d rows", metaPath, rows)
	}
	if j.Path == "" {
		return nil, fmt.Errorf("%s: no source DB path", metaPath)
	}
	m := &retrieveMeta{ts: make([]string, rows), util: j.Util, etype: j.EType, path: j.Path, maxID: j.MaxID}
	for i, t := range j.TS {
		if t != nil {
			m.ts[i] = *t
		}
	}
	for _, r := range j.Legacy {
		row, err := parseLegacyJSON(r)
		if err != nil {
			return nil, fmt.Errorf("%s: legacy row: %w", metaPath, err)
		}
		m.legacy = append(m.legacy, row)
	}
	return m, nil
}

// parseLegacyJSON reads [id, utility, timestamp, domain, etype, emb], where
// emb is a string (JSON text) or {"hex": "..."} (raw bytes).
func parseLegacyJSON(r []json.RawMessage) (legacyRow, error) {
	var row legacyRow
	if len(r) != 6 {
		return row, fmt.Errorf("want 6 fields, got %d", len(r))
	}
	if err := json.Unmarshal(r[0], &row.id); err != nil {
		return row, err
	}
	var util *float64
	var ts, dom, typ *string
	if err := json.Unmarshal(r[1], &util); err != nil {
		return row, err
	}
	if err := json.Unmarshal(r[2], &ts); err != nil {
		return row, err
	}
	if err := json.Unmarshal(r[3], &dom); err != nil {
		return row, err
	}
	if err := json.Unmarshal(r[4], &typ); err != nil {
		return row, err
	}
	if util != nil {
		row.util = *util
	}
	if ts != nil {
		row.ts = *ts
	}
	if dom != nil {
		row.dom = *dom
	}
	if typ != nil {
		row.typ = *typ
	}
	var asHex struct {
		Hex *string `json:"hex"`
	}
	if err := json.Unmarshal(r[5], &asHex); err == nil && asHex.Hex != nil {
		b, err := hex.DecodeString(*asHex.Hex)
		if err != nil {
			return row, err
		}
		row.emb = b
		return row, nil
	}
	var text string
	if err := json.Unmarshal(r[5], &text); err != nil {
		return row, fmt.Errorf("embedding is neither text nor hex")
	}
	row.emb = []byte(text)
	return row, nil
}

// tailRows are the rows written since the sidecar was saved.
type tailRows struct {
	ids    []int64
	ts     []string
	util   []float32
	dom    []string
	etype  []string
	data   []float32 // len(ids) * dim
	legacy []legacyRow
}

// retrieveState is what retrieve knows about one DB beyond its mapped matrix.
type retrieveState struct {
	mu         sync.Mutex
	key        string // which sidecar this was built for
	meta       *retrieveMeta
	sig        string // DB write signature the fields below were read at
	tail       tailRows
	dead       []bool // base rows deleted since the save; nil when none
	nDead      int
	baseLegacy []legacyRow
	fallback   bool
	nEmbedded  int    // embedded rows in the DB at sig
	dbMaxID    int64  // highest embedded id in the DB at sig
	savedSig   string // sig a sidecar save was last attempted at
}

var retrieveStates = struct {
	sync.Mutex
	byDB map[int]*retrieveState
	dbs  map[string]*sql.DB
}{byDB: map[int]*retrieveState{}, dbs: map[string]*sql.DB{}}

func stateFor(db int) *retrieveState {
	retrieveStates.Lock()
	defer retrieveStates.Unlock()
	st := retrieveStates.byDB[db]
	if st == nil {
		st = &retrieveState{}
		retrieveStates.byDB[db] = st
	}
	return st
}

func openReadOnly(path string) (*sql.DB, error) {
	retrieveStates.Lock()
	defer retrieveStates.Unlock()
	if db := retrieveStates.dbs[path]; db != nil {
		return db, nil
	}
	dsn := (&url.URL{Scheme: "file", Path: path}).String() + "?mode=ro&_pragma=busy_timeout(5000)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(2)
	retrieveStates.dbs[path] = db
	return db, nil
}

// dbWriteSignature mirrors core._db_write_signature: whole-second mtime and
// size of the DB file and of its -wal, where a WAL-mode write lands first.
func dbWriteSignature(path string) string {
	var b strings.Builder
	for _, suffix := range []string{"", "-wal"} {
		if st, err := os.Stat(path + suffix); err == nil {
			fmt.Fprintf(&b, "%d:%d;", st.ModTime().Unix(), st.Size())
		} else {
			b.WriteString("-;")
		}
	}
	return b.String()
}

func upper(s sql.NullString) string { return strings.ToUpper(s.String) }

// refreshState brings st up to date with the DB behind m. Called with st.mu held.
func (st *retrieveState) refresh(m *dbMatrix) error {
	key := m.npyPath + "|" + m.sha256
	if st.key != key {
		meta, err := loadRetrieveMeta(strings.TrimSuffix(m.npyPath, ".npy")+".json", m.rows)
		if err != nil {
			return err
		}
		// Field by field: st.mu is held by the caller and must not be copied over.
		st.key, st.meta, st.sig = key, meta, ""
		st.tail, st.dead, st.nDead, st.baseLegacy, st.fallback = tailRows{}, nil, 0, nil, false
		st.savedSig = ""
	}
	sig := dbWriteSignature(st.meta.path)
	if sig == st.sig {
		return nil
	}
	db, err := openReadOnly(st.meta.path)
	if err != nil {
		return err
	}
	var nEmbedded int
	var maxID int64
	if err := db.QueryRow("SELECT COUNT(*), COALESCE(MAX(id), 0) FROM shards WHERE embedding IS NOT NULL").
		Scan(&nEmbedded, &maxID); err != nil {
		return err
	}
	tail, err := readTail(db, st.meta.maxID, m.dim)
	if err != nil {
		return err
	}
	var dead []bool
	nDead := 0
	baseLegacy := st.meta.legacy
	fallback := false
	have := m.rows + len(baseLegacy) + len(tail.ids) + len(tail.legacy)
	if have != nEmbedded {
		// A base row was deleted, or an old row gained an embedding (backfill).
		live, err := liveIDs(db, st.meta.maxID)
		if err != nil {
			return err
		}
		dead = make([]bool, m.rows)
		for i, id := range m.ids {
			if !live[id] {
				dead[i] = true
				nDead++
			}
		}
		kept := make([]legacyRow, 0, len(baseLegacy))
		for _, r := range baseLegacy {
			if live[r.id] {
				kept = append(kept, r)
			}
		}
		baseLegacy = kept
		// A backfill leaves a live id this copy has never seen: not answerable here.
		fallback = m.rows-nDead+len(baseLegacy)+len(tail.ids)+len(tail.legacy) != nEmbedded
	}
	st.tail, st.dead, st.nDead, st.baseLegacy, st.fallback, st.sig = tail, dead, nDead, baseLegacy, fallback, sig
	st.nEmbedded, st.dbMaxID = nEmbedded, maxID
	return nil
}

func readTail(db *sql.DB, sinceID int64, dim int) (tailRows, error) {
	var t tailRows
	rows, err := db.Query(`SELECT id, timestamp, utility_score, domain_key, event_type, embedding
		FROM shards WHERE embedding IS NOT NULL AND id > ? ORDER BY id ASC`, sinceID)
	if err != nil {
		return t, err
	}
	defer rows.Close()
	for rows.Next() {
		var id int64
		var ts, dom, typ sql.NullString
		var util sql.NullFloat64
		var emb []byte
		if err := rows.Scan(&id, &ts, &util, &dom, &typ, &emb); err != nil {
			return t, err
		}
		if len(emb) > 0 && len(emb)%4 == 0 && emb[0] != '[' && len(emb)/4 == dim {
			t.ids = append(t.ids, id)
			t.ts = append(t.ts, ts.String)
			t.util = append(t.util, float32(util.Float64))
			t.dom = append(t.dom, dom.String)
			t.etype = append(t.etype, upper(typ))
			for o := 0; o < len(emb); o += 4 {
				t.data = append(t.data, math.Float32frombits(binary.LittleEndian.Uint32(emb[o:])))
			}
			continue
		}
		t.legacy = append(t.legacy, legacyRow{id: id, util: util.Float64, ts: ts.String,
			dom: dom.String, typ: upper(typ), emb: append([]byte(nil), emb...)})
	}
	return t, rows.Err()
}

func liveIDs(db *sql.DB, maxID int64) (map[int64]bool, error) {
	rows, err := db.Query("SELECT id FROM shards WHERE embedding IS NOT NULL AND id <= ?", maxID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	live := map[int64]bool{}
	for rows.Next() {
		var id int64
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		live[id] = true
	}
	return live, rows.Err()
}

var pyISOLayouts = []string{
	"2006-01-02T15:04:05.999999999Z07:00",
	"2006-01-02T15:04:05.999999999Z0700",
	"2006-01-02T15:04:05.999999999",
	"2006-01-02T15:04Z07:00",
	"2006-01-02T15:04",
	"2006-01-02",
}

// parsePyISO accepts what Python's datetime.fromisoformat(ts.replace("Z",
// "+00:00")) accepts among the forms the vault holds, and nothing it rejects
// ("2026-09-12 12:49:23 AM" fails there, so it fails here). No offset is UTC.
func parsePyISO(ts string) (time.Time, bool) {
	if len(ts) < 10 {
		return time.Time{}, false
	}
	s := strings.ReplaceAll(ts, "Z", "+00:00")
	if len(s) > 10 && s[10] == ' ' {
		s = s[:10] + "T" + s[11:]
	}
	for _, layout := range pyISOLayouts {
		if t, err := time.Parse(layout, s); err == nil {
			return t, true
		}
	}
	return time.Time{}, false
}

// temporalDecay mirrors core._temporal_decay: a 30-day half-life floored at
// 0.1; a missing or unreadable timestamp does not decay.
func temporalDecay(ts string, now time.Time) float64 {
	if ts == "" {
		return 1.0
	}
	t, ok := parsePyISO(ts)
	if !ok {
		return 1.0
	}
	ageDays := now.Sub(t).Seconds() / 86400.0
	return math.Max(0.1, math.Pow(0.5, ageDays/30.0))
}

// legacySem mirrors the per-row fallback: JSON text or raw float32; a width
// other than the query's, or anything unreadable, scores 0.
func legacySem(emb []byte, q []float32) float64 {
	var vec []float32
	if len(emb) > 0 && emb[0] == '[' {
		if err := json.Unmarshal(emb, &vec); err != nil {
			return 0
		}
	} else {
		if len(emb)%4 != 0 {
			return 0
		}
		vec = make([]float32, len(emb)/4)
		for i := range vec {
			vec[i] = math.Float32frombits(binary.LittleEndian.Uint32(emb[i*4:]))
		}
	}
	if len(vec) != len(q) {
		return 0
	}
	return float64(dot(vec, q))
}

type semRow struct {
	sem  float32
	id   int64
	util float32
	ts   string
}

type semHeap []semRow // min-heap on sem

func (h semHeap) Len() int            { return len(h) }
func (h semHeap) Less(i, j int) bool  { return h[i].sem < h[j].sem }
func (h semHeap) Swap(i, j int)       { h[i], h[j] = h[j], h[i] }
func (h *semHeap) Push(x interface{}) { *h = append(*h, x.(semRow)) }
func (h *semHeap) Pop() interface{} {
	old := *h
	x := old[len(old)-1]
	*h = old[:len(old)-1]
	return x
}

// scoreDB ranks one DB. Called with st.mu held and st fresh.
func scoreDB(m *dbMatrix, st *retrieveState, q []float32, limit int, domain string,
	excluded map[string]bool, now time.Time) []scoredRow {
	filter := domain != "" && domain != "*"
	// Only a semantic-top pool gets the exact (decayed) score, as in Python:
	// the prior term is bounded, so a generous pool cannot drop a row that
	// exact scoring would have put in the top `limit`.
	n := m.rows - st.nDead + len(st.tail.ids)
	poolN := limit * 8
	if poolN < 256 {
		poolN = 256
	}
	if poolN > n {
		poolN = n
	}
	pool := make(semHeap, 0, poolN)
	offer := func(r semRow) {
		if len(pool) < poolN {
			heap.Push(&pool, r)
		} else if poolN > 0 && r.sem > pool[0].sem {
			pool[0] = r
			heap.Fix(&pool, 0)
		}
	}
	for r := 0; r < m.rows; r++ {
		if (st.dead != nil && st.dead[r]) || (filter && m.dom[r] != domain) || excluded[st.meta.etype[r]] {
			continue
		}
		offer(semRow{dot(m.data[r*m.dim:(r+1)*m.dim], q), m.ids[r], st.meta.util[r], st.meta.ts[r]})
	}
	t := &st.tail
	for r := range t.ids {
		if (filter && t.dom[r] != domain) || excluded[t.etype[r]] {
			continue
		}
		offer(semRow{dot(t.data[r*m.dim:(r+1)*m.dim], q), t.ids[r], t.util[r], t.ts[r]})
	}
	out := make([]scoredRow, 0, len(pool)+len(st.baseLegacy)+len(t.legacy))
	for _, r := range pool {
		out = append(out, scoredRow{m.db, r.id,
			float64(r.sem)*weightLikelihood + float64(r.util)*temporalDecay(r.ts, now)*weightPrior})
	}
	for _, rows := range [][]legacyRow{st.baseLegacy, t.legacy} {
		for _, r := range rows {
			if (filter && r.dom != domain) || excluded[r.typ] {
				continue
			}
			out = append(out, scoredRow{m.db, r.id,
				legacySem(r.emb, q)*weightLikelihood + r.util*temporalDecay(r.ts, now)*weightPrior})
		}
	}
	sort.Slice(out, func(i, j int) bool {
		if out[i].FinalScore != out[j].FinalScore {
			return out[i].FinalScore > out[j].FinalScore
		}
		return out[i].ID < out[j].ID
	})
	if len(out) > limit {
		out = out[:limit]
	}
	return out
}

func (ix *vectorIndex) retrieve(req retrieveRequest) retrieveResult {
	res := retrieveResult{Rows: []scoredRow{}, DBs: []int{}, Fallback: []int{}, Skipped: []int{}, Paths: map[string]string{}}
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}
	now := time.Now().UTC()
	if req.Now != "" {
		if t, err := time.Parse(time.RFC3339Nano, req.Now); err == nil {
			now = t
		}
	}
	excluded := make(map[string]bool, len(req.ExcludedTypes))
	for _, t := range req.ExcludedTypes {
		excluded[t] = true
	}
	ix.mu.RLock()
	defer ix.mu.RUnlock()
	var wg sync.WaitGroup
	var mu sync.Mutex
	for _, m := range ix.dbs {
		wg.Add(1)
		go func(m *dbMatrix) {
			defer wg.Done()
			st := stateFor(m.db)
			st.mu.Lock()
			defer st.mu.Unlock()
			err := st.refresh(m)
			var rows []scoredRow
			outcome := &res.DBs
			switch {
			case err != nil:
				log.Printf("vector retrieve: DB %d handed back to the caller: %v", m.db, err)
				st.sig = "" // do not remember a failed read
				outcome = &res.Fallback
			case st.fallback:
				outcome = &res.Fallback
			case m.dim != len(req.Embedding):
				if m.rows-st.nDead+len(st.tail.ids) > 0 {
					outcome = &res.Skipped
				}
			default:
				rows = scoreDB(m, st, req.Embedding, limit, req.DomainKey, excluded, now)
			}
			if err == nil && st.needsSave() {
				st.save(m)
			}
			mu.Lock()
			*outcome = append(*outcome, m.db)
			if st.meta != nil {
				res.Paths[fmt.Sprint(m.db)] = st.meta.path
			}
			res.Rows = append(res.Rows, rows...)
			mu.Unlock()
		}(m)
	}
	wg.Wait()
	sort.Slice(res.Rows, func(i, j int) bool {
		a, b := res.Rows[i], res.Rows[j]
		if a.FinalScore != b.FinalScore {
			return a.FinalScore > b.FinalScore
		}
		if a.DB != b.DB {
			return a.DB < b.DB
		}
		return a.ID < b.ID
	})
	if len(res.Rows) > limit {
		res.Rows = res.Rows[:limit]
	}
	sort.Ints(res.DBs)
	sort.Ints(res.Fallback)
	sort.Ints(res.Skipped)
	return res
}

func (n *node) handleVectorRetrieve(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		w.Header().Set("Allow", "POST")
		writeJSON(w, http.StatusMethodNotAllowed, map[string]string{"detail": "POST only"})
		return
	}
	if !n.authed(w, r) {
		return
	}
	var req retrieveRequest
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, maxSearchBody)).Decode(&req); err != nil {
		writeJSON(w, http.StatusBadRequest, map[string]string{"detail": "bad JSON body: " + err.Error()})
		return
	}
	if len(req.Embedding) == 0 {
		writeJSON(w, http.StatusBadRequest, map[string]string{"detail": "embedding is required"})
		return
	}
	for _, e := range n.index.refresh() {
		log.Printf("vector index: %v", e)
	}
	writeJSON(w, http.StatusOK, n.index.retrieve(req))
}
