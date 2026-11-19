package main

// Saving a DB's matrix, in the format core._save_vector_sidecar writes and
// core._load_vector_sidecar reads.
//
// With the vector lane served here, the Python worker no longer builds its
// cache, so it no longer saves these files. Without a writer the rows read
// from SQLite on every write (the tail) would only grow. Once a tail reaches
// sidecarResaveRows the pair is rewritten: live saved rows plus the tail. The
// next index refresh maps the new file and the tail starts empty again.

import (
	"bufio"
	"crypto/sha256"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"os"
	"strconv"
	"strings"
	"time"
	"unsafe"
)

// sidecarResaveRows mirrors core._VECTOR_SIDECAR_RESAVE_ROWS.
var sidecarResaveRows = envInt("NGS_SIDECAR_RESAVE_ROWS", 512)

// sidecarLockStale mirrors core._VECTOR_SIDECAR_LOCK_STALE_S.
const sidecarLockStale = 600 * time.Second

func envInt(key string, fallback int) int {
	if n, err := strconv.Atoi(strings.TrimSpace(os.Getenv(key))); err == nil && n > 0 {
		return n
	}
	return fallback
}

// acquireSidecarLock is the cross-process save lock the Python node uses:
// an exclusive-create file beside the matrix. The loser skips its save.
func acquireSidecarLock(path string) bool {
	for attempt := 0; attempt < 2; attempt++ {
		f, err := os.OpenFile(path, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0o644)
		if err == nil {
			_, _ = f.WriteString(strconv.Itoa(os.Getpid()))
			_ = f.Close()
			return true
		}
		if !os.IsExist(err) {
			return false
		}
		st, err := os.Stat(path)
		if err != nil || time.Since(st.ModTime()) < sidecarLockStale {
			return false
		}
		if os.Remove(path) != nil { // left by a crashed writer: take it over once
			return false
		}
	}
	return false
}

func float32Bytes(v []float32) []byte {
	if len(v) == 0 {
		return nil
	}
	return unsafe.Slice((*byte)(unsafe.Pointer(&v[0])), len(v)*4)
}

// needsSave reports whether st's tail is long enough to fold into the file.
func (st *retrieveState) needsSave() bool {
	return !st.fallback && st.sig != "" && st.sig != st.savedSig &&
		len(st.tail.ids)+len(st.tail.legacy) >= sidecarResaveRows
}

// save rewrites m's sidecar pair from m, st's dead mask and st's tail. Called
// with st.mu held and the index read-locked, so m stays mapped. Best effort:
// a failed or skipped save costs nothing but the next attempt.
func (st *retrieveState) save(m *dbMatrix) {
	st.savedSig = st.sig // one attempt per DB state, whatever the outcome
	npy := m.npyPath
	meta := strings.TrimSuffix(npy, ".npy") + ".json"
	lock := npy + ".lock"
	live := m.rows - st.nDead
	rows := live + len(st.tail.ids)
	if rows == 0 {
		return // an emptied DB's files are removed by the Python writer
	}
	if !acquireSidecarLock(lock) {
		return
	}
	defer os.Remove(lock)
	tag := fmt.Sprintf(".%d.go.tmp", os.Getpid())
	tmpNpy, tmpMeta := npy+tag+".npy", meta+tag
	defer os.Remove(tmpNpy)
	defer os.Remove(tmpMeta)
	started := time.Now()

	ids := make([]int64, 0, rows)
	ts := make([]string, 0, rows)
	util := make([]float64, 0, rows)
	dom := make([]string, 0, rows)
	etype := make([]string, 0, rows)
	sum, err := func() (string, error) {
		f, err := os.OpenFile(tmpNpy, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, 0o644)
		if err != nil {
			return "", err
		}
		defer f.Close()
		w := bufio.NewWriterSize(f, 1<<20)
		// numpy's v1 header: the dict, space-padded so the data starts on a
		// 64-byte boundary, newline-terminated.
		header := fmt.Sprintf("{'descr': '<f4', 'fortran_order': False, 'shape': (%d, %d), }", rows, m.dim)
		for (10+len(header)+1)%64 != 0 {
			header += " "
		}
		header += "\n"
		if _, err := w.WriteString("\x93NUMPY\x01\x00"); err != nil {
			return "", err
		}
		if err := binary.Write(w, binary.LittleEndian, uint16(len(header))); err != nil {
			return "", err
		}
		if _, err := w.WriteString(header); err != nil {
			return "", err
		}
		digest := sha256.New()
		out := io.MultiWriter(w, digest)
		for r := 0; r < m.rows; r++ {
			if st.dead != nil && st.dead[r] {
				continue
			}
			if _, err := out.Write(float32Bytes(m.data[r*m.dim : (r+1)*m.dim])); err != nil {
				return "", err
			}
			ids, ts, util = append(ids, m.ids[r]), append(ts, st.meta.ts[r]), append(util, float64(st.meta.util[r]))
			dom, etype = append(dom, m.dom[r]), append(etype, st.meta.etype[r])
		}
		t := &st.tail
		if _, err := out.Write(float32Bytes(t.data)); err != nil {
			return "", err
		}
		for r := range t.ids {
			ids, ts, util = append(ids, t.ids[r]), append(ts, t.ts[r]), append(util, float64(t.util[r]))
			dom, etype = append(dom, t.dom[r]), append(etype, t.etype[r])
		}
		if err := w.Flush(); err != nil {
			return "", err
		}
		return hex.EncodeToString(digest.Sum(nil)), f.Sync()
	}()
	if err != nil {
		log.Printf("vector sidecar: DB %d not saved: %v", m.db, err)
		return
	}
	legacy := make([][]interface{}, 0, len(st.baseLegacy)+len(st.tail.legacy))
	for _, group := range [][]legacyRow{st.baseLegacy, st.tail.legacy} {
		for _, r := range group {
			legacy = append(legacy, []interface{}{r.id, r.util, r.ts, r.dom, r.typ,
				map[string]string{"hex": hex.EncodeToString(r.emb)}})
		}
	}
	raw, err := json.Marshal(map[string]interface{}{
		"v": 2, "path": st.meta.path, "dim": m.dim, "n_embedded": st.nEmbedded, "max_id": st.dbMaxID,
		"sha256": sum, "ids": ids, "ts": ts, "util": util, "dom": dom, "etype": etype, "legacy": legacy,
	})
	if err == nil {
		err = os.WriteFile(tmpMeta, raw, 0o644)
	}
	if err != nil {
		log.Printf("vector sidecar: DB %d not saved: %v", m.db, err)
		return
	}
	// Matrix first, metadata last: a reader that sees the new metadata checks
	// it against the matrix, so a half-swapped pair is rejected.
	if err := os.Rename(tmpNpy, npy); err != nil {
		log.Printf("vector sidecar: DB %d not saved: %v", m.db, err)
		return
	}
	if err := os.Rename(tmpMeta, meta); err != nil {
		log.Printf("vector sidecar: DB %d metadata not replaced: %v", m.db, err)
		return
	}
	log.Printf("vector sidecar: DB %d saved, %d rows (%d from the tail, %d deleted) in %s",
		m.db, rows, len(st.tail.ids), st.nDead, time.Since(started).Round(time.Millisecond))
}
