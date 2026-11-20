package main

import (
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"sort"
	"strings"
	"sync"
	"time"

	_ "modernc.org/sqlite" // pure-Go SQLite driver: no cgo, one static binary
)

// AuthStore holds, per node id, the sha256 hex of that node's join token. The
// token itself is never stored. This replaces the Worker's RELAY_AUTH KV
// namespace (key "relay:<id>", value sha256 hex).
type AuthStore interface {
	Hash(id string) (hash string, found bool, err error)
	Put(id, hash string) error
	IDs() ([]string, error)
	Close() error
}

// MemStore is an in-memory AuthStore for tests.
type MemStore struct {
	mu sync.Mutex
	m  map[string]string
}

func NewMemStore() *MemStore { return &MemStore{m: map[string]string{}} }

func (s *MemStore) Hash(id string) (string, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	h, ok := s.m[id]
	return h, ok, nil
}

func (s *MemStore) Put(id, hash string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.m[id] = hash
	return nil
}

func (s *MemStore) IDs() ([]string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := make([]string, 0, len(s.m))
	for k := range s.m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out, nil
}

func (s *MemStore) Close() error { return nil }

// SQLiteStore keeps the records in a local SQLite file.
type SQLiteStore struct{ db *sql.DB }

// OpenSQLite opens (and creates) the auth database at path.
func OpenSQLite(path string) (*SQLiteStore, error) {
	db, err := sql.Open("sqlite", "file:"+path+"?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)")
	if err != nil {
		return nil, err
	}
	db.SetMaxOpenConns(1) // one writer; the record set is tiny
	if _, err := db.Exec(`CREATE TABLE IF NOT EXISTS relay_auth (
		id          TEXT PRIMARY KEY,
		sha256      TEXT NOT NULL,
		updated_utc TEXT NOT NULL
	)`); err != nil {
		db.Close()
		return nil, err
	}
	return &SQLiteStore{db: db}, nil
}

func (s *SQLiteStore) Hash(id string) (string, bool, error) {
	var h string
	err := s.db.QueryRow(`SELECT sha256 FROM relay_auth WHERE id = ?`, id).Scan(&h)
	if errors.Is(err, sql.ErrNoRows) {
		return "", false, nil
	}
	if err != nil {
		return "", false, err
	}
	return h, true, nil
}

func (s *SQLiteStore) Put(id, hash string) error {
	_, err := s.db.Exec(`INSERT INTO relay_auth (id, sha256, updated_utc) VALUES (?, ?, ?)
		ON CONFLICT(id) DO UPDATE SET sha256 = excluded.sha256, updated_utc = excluded.updated_utc`,
		id, hash, time.Now().UTC().Format(time.RFC3339))
	return err
}

func (s *SQLiteStore) IDs() ([]string, error) {
	rows, err := s.db.Query(`SELECT id FROM relay_auth ORDER BY id`)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []string
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return nil, err
		}
		out = append(out, id)
	}
	return out, rows.Err()
}

func (s *SQLiteStore) Close() error { return s.db.Close() }

var hexRE = func(s string) bool {
	if len(s) != 64 {
		return false
	}
	for _, c := range s {
		if !(c >= '0' && c <= '9' || c >= 'a' && c <= 'f') {
			return false
		}
	}
	return true
}

// ImportKV loads records exported from the Worker's RELAY_AUTH namespace. The file is
// the JSON array wrangler produces for a bulk listing with values:
// [{"key":"relay:<id>","value":"<sha256 hex>"}, ...]. Bad rows are reported, not
// skipped silently; nothing is written unless every row is valid.
func ImportKV(st AuthStore, path string) (int, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return 0, err
	}
	var rows []struct {
		Key   string `json:"key"`
		Value string `json:"value"`
	}
	if err := json.Unmarshal(raw, &rows); err != nil {
		return 0, fmt.Errorf("not a JSON array of {key,value}: %w", err)
	}
	type rec struct{ id, hash string }
	var recs []rec
	for i, r := range rows {
		id := strings.TrimPrefix(r.Key, "relay:")
		if !validID(id) || id == r.Key {
			return 0, fmt.Errorf("row %d: key %q is not relay:<id>", i, r.Key)
		}
		if !hexRE(r.Value) {
			return 0, fmt.Errorf("row %d (%s): value is not a sha256 hex digest", i, id)
		}
		recs = append(recs, rec{id, r.Value})
	}
	for _, r := range recs {
		if err := st.Put(r.id, r.hash); err != nil {
			return 0, err
		}
	}
	return len(recs), nil
}
