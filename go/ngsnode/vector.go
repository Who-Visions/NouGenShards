package main

// The vector lane: exact cosine search over the per-DB matrices the Python
// node saves under <vault>/.vector-cache (core._save_vector_sidecar).
//
// Each DB has a pair: dbN-<key>.npy (float32, C order, shape (rows, dim)) and
// dbN-<key>.json (ids, domain keys and the matrix sha256). The matrices are
// memory-mapped read-only, so their pages are file-backed: the OS drops them
// under memory pressure and pages them back in, and nothing here is heap.

import (
	"container/heap"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"sync"
	"syscall"
	"unsafe"
)

type sidecarMeta struct {
	V      int      `json:"v"`
	Dim    int      `json:"dim"`
	SHA256 string   `json:"sha256"`
	IDs    []int64  `json:"ids"`
	Dom    []string `json:"dom"`
}

type dbMatrix struct {
	db      int
	npyPath string
	modTime int64
	size    int64
	rows    int
	dim     int
	ids     []int64
	dom     []string
	sha256  string
	mapped  []byte    // whole file, for Munmap
	data    []float32 // rows*dim view into mapped
}

func (m *dbMatrix) close() {
	if m.mapped != nil {
		_ = syscall.Munmap(m.mapped)
		m.mapped, m.data = nil, nil
	}
}

var npyShapeRe = regexp.MustCompile(`'shape':\s*\((\d+),\s*(\d+)\)`)
var npyDescrRe = regexp.MustCompile(`'descr':\s*'([^']+)'`)
var npyFortranRe = regexp.MustCompile(`'fortran_order':\s*(True|False)`)

// parseNpyHeader returns the data offset and (rows, dim) of a 2-D little-endian
// float32 C-order .npy file. Anything else is an error, never a guess.
func parseNpyHeader(b []byte) (offset, rows, dim int, err error) {
	if len(b) < 10 || string(b[:6]) != "\x93NUMPY" {
		return 0, 0, 0, errors.New("not an npy file")
	}
	var hlen, start int
	switch b[6] {
	case 1:
		hlen, start = int(binary.LittleEndian.Uint16(b[8:10])), 10
	case 2, 3:
		if len(b) < 12 {
			return 0, 0, 0, errors.New("truncated npy header")
		}
		hlen, start = int(binary.LittleEndian.Uint32(b[8:12])), 12
	default:
		return 0, 0, 0, fmt.Errorf("unsupported npy version %d", b[6])
	}
	if start+hlen > len(b) {
		return 0, 0, 0, errors.New("truncated npy header")
	}
	h := string(b[start : start+hlen])
	d := npyDescrRe.FindStringSubmatch(h)
	if d == nil || (d[1] != "<f4" && d[1] != "|f4") {
		return 0, 0, 0, fmt.Errorf("npy dtype is not little-endian float32: %q", h)
	}
	f := npyFortranRe.FindStringSubmatch(h)
	if f == nil || f[1] != "False" {
		return 0, 0, 0, errors.New("npy is not C order")
	}
	s := npyShapeRe.FindStringSubmatch(h)
	if s == nil {
		return 0, 0, 0, fmt.Errorf("npy is not 2-D: %q", h)
	}
	rows, _ = strconv.Atoi(s[1])
	dim, _ = strconv.Atoi(s[2])
	offset = start + hlen
	if offset%4 != 0 {
		return 0, 0, 0, errors.New("npy data is not 4-byte aligned")
	}
	if offset+rows*dim*4 > len(b) {
		return 0, 0, 0, errors.New("npy data is shorter than its shape")
	}
	return offset, rows, dim, nil
}

func openMatrix(db int, npyPath, metaPath string) (*dbMatrix, error) {
	raw, err := os.ReadFile(metaPath)
	if err != nil {
		return nil, err
	}
	var meta sidecarMeta
	if err := json.Unmarshal(raw, &meta); err != nil {
		return nil, fmt.Errorf("%s: %w", metaPath, err)
	}
	if meta.V != 2 {
		return nil, fmt.Errorf("%s: sidecar version %d, want 2", metaPath, meta.V)
	}
	f, err := os.Open(npyPath)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	st, err := f.Stat()
	if err != nil {
		return nil, err
	}
	if st.Size() == 0 {
		return nil, errors.New("empty npy")
	}
	mapped, err := syscall.Mmap(int(f.Fd()), 0, int(st.Size()), syscall.PROT_READ, syscall.MAP_SHARED)
	if err != nil {
		return nil, fmt.Errorf("mmap %s: %w", npyPath, err)
	}
	off, rows, dim, err := parseNpyHeader(mapped)
	if err == nil && (rows != len(meta.IDs) || dim != meta.Dim || len(meta.Dom) != rows) {
		// The Python writer replaces the matrix first and the metadata last, so
		// a reader can catch the pair mid-swap. Skip it; the next refresh sees
		// the finished pair.
		err = fmt.Errorf("%s: matrix %dx%d does not match metadata (%d ids, dim %d)",
			npyPath, rows, dim, len(meta.IDs), meta.Dim)
	}
	if err != nil {
		_ = syscall.Munmap(mapped)
		return nil, err
	}
	m := &dbMatrix{db: db, npyPath: npyPath, modTime: st.ModTime().UnixNano(), size: st.Size(),
		rows: rows, dim: dim, ids: meta.IDs, dom: meta.Dom, sha256: meta.SHA256, mapped: mapped}
	if rows*dim > 0 {
		m.data = unsafe.Slice((*float32)(unsafe.Pointer(&mapped[off])), rows*dim)
	}
	return m, nil
}

// vectorIndex is the set of mapped matrices for one vault.
type vectorIndex struct {
	dir string
	mu  sync.RWMutex
	dbs map[int]*dbMatrix
}

func newVectorIndex(vaultDir string) *vectorIndex {
	return &vectorIndex{dir: filepath.Join(vaultDir, ".vector-cache"), dbs: map[int]*dbMatrix{}}
}

var sidecarNameRe = regexp.MustCompile(`^db(\d+)-[0-9a-f]+\.npy$`)

// refresh maps new or rewritten sidecars and drops ones that are gone. It is
// cheap when nothing changed (one ReadDir plus a stat per matrix).
func (ix *vectorIndex) refresh() []error {
	entries, err := os.ReadDir(ix.dir)
	if err != nil {
		if os.IsNotExist(err) {
			return nil
		}
		return []error{err}
	}
	type cand struct {
		path string
		mod  int64
		size int64
	}
	newest := map[int]cand{}
	for _, e := range entries {
		mm := sidecarNameRe.FindStringSubmatch(e.Name())
		if mm == nil {
			continue
		}
		info, err := e.Info()
		if err != nil {
			continue
		}
		db, _ := strconv.Atoi(mm[1])
		c := cand{filepath.Join(ix.dir, e.Name()), info.ModTime().UnixNano(), info.Size()}
		if cur, ok := newest[db]; !ok || c.mod > cur.mod {
			newest[db] = c
		}
	}
	var errs []error
	ix.mu.Lock()
	defer ix.mu.Unlock()
	for db, c := range newest {
		if cur, ok := ix.dbs[db]; ok && cur.npyPath == c.path && cur.modTime == c.mod && cur.size == c.size {
			continue
		}
		meta := c.path[:len(c.path)-len(".npy")] + ".json"
		m, err := openMatrix(db, c.path, meta)
		if err != nil {
			errs = append(errs, err) // keep serving the previous mapping, if any
			continue
		}
		if cur, ok := ix.dbs[db]; ok {
			cur.close()
		}
		ix.dbs[db] = m
	}
	for db, cur := range ix.dbs {
		if _, ok := newest[db]; !ok {
			cur.close()
			delete(ix.dbs, db)
		}
	}
	return errs
}

type hit struct {
	DB    int     `json:"db"`
	ID    int64   `json:"id"`
	Score float32 `json:"score"`
}

type hitHeap []hit // min-heap on score

func (h hitHeap) Len() int            { return len(h) }
func (h hitHeap) Less(i, j int) bool  { return h[i].Score < h[j].Score }
func (h hitHeap) Swap(i, j int)       { h[i], h[j] = h[j], h[i] }
func (h *hitHeap) Push(x interface{}) { *h = append(*h, x.(hit)) }
func (h *hitHeap) Pop() interface{} {
	old := *h
	x := old[len(old)-1]
	*h = old[:len(old)-1]
	return x
}

func dot(a, b []float32) float32 {
	var s0, s1, s2, s3 float32
	n := len(a) &^ 3
	for i := 0; i < n; i += 4 {
		s0 += a[i] * b[i]
		s1 += a[i+1] * b[i+1]
		s2 += a[i+2] * b[i+2]
		s3 += a[i+3] * b[i+3]
	}
	for i := n; i < len(a); i++ {
		s0 += a[i] * b[i]
	}
	return s0 + s1 + s2 + s3
}

func (m *dbMatrix) topK(q []float32, k int, domain string) []hit {
	h := make(hitHeap, 0, k)
	filter := domain != "" && domain != "*"
	for r := 0; r < m.rows; r++ {
		if filter && m.dom[r] != domain {
			continue
		}
		s := dot(m.data[r*m.dim:(r+1)*m.dim], q)
		if len(h) < k {
			heap.Push(&h, hit{m.db, m.ids[r], s})
		} else if s > h[0].Score {
			h[0] = hit{m.db, m.ids[r], s}
			heap.Fix(&h, 0)
		}
	}
	return h
}

type searchResult struct {
	Hits    []hit `json:"hits"`
	Rows    int   `json:"rows"`
	DBs     []int `json:"dbs"`
	Skipped []int `json:"skipped_dim_mismatch"`
}

// search returns the topN rows by dot product across every mapped DB. The
// stored embeddings are L2-normalised, so this is cosine similarity, exact.
func (ix *vectorIndex) search(q []float32, topN int, domain string) searchResult {
	ix.mu.RLock()
	defer ix.mu.RUnlock()
	res := searchResult{Hits: []hit{}, DBs: []int{}, Skipped: []int{}}
	var wg sync.WaitGroup
	var mu sync.Mutex
	for _, m := range ix.dbs {
		if m.dim != len(q) {
			res.Skipped = append(res.Skipped, m.db)
			continue
		}
		res.DBs = append(res.DBs, m.db)
		res.Rows += m.rows
		wg.Add(1)
		go func(m *dbMatrix) {
			defer wg.Done()
			part := m.topK(q, topN, domain)
			mu.Lock()
			res.Hits = append(res.Hits, part...)
			mu.Unlock()
		}(m)
	}
	wg.Wait()
	sort.Slice(res.Hits, func(i, j int) bool {
		a, b := res.Hits[i], res.Hits[j]
		if a.Score != b.Score {
			return a.Score > b.Score
		}
		if a.DB != b.DB {
			return a.DB < b.DB
		}
		return a.ID < b.ID
	})
	if len(res.Hits) > topN {
		res.Hits = res.Hits[:topN]
	}
	sort.Ints(res.DBs)
	sort.Ints(res.Skipped)
	return res
}

type indexStatus struct {
	DB     int    `json:"db"`
	Rows   int    `json:"rows"`
	Dim    int    `json:"dim"`
	SHA256 string `json:"sha256"`
}

func (ix *vectorIndex) status() []indexStatus {
	ix.mu.RLock()
	defer ix.mu.RUnlock()
	out := make([]indexStatus, 0, len(ix.dbs))
	for _, m := range ix.dbs {
		out = append(out, indexStatus{m.db, m.rows, m.dim, m.sha256})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].DB < out[j].DB })
	return out
}
