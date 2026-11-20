package main

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"sync"
	"time"

	"github.com/gorilla/websocket"
)

// session is one connected node. One node, one session: a newer connect for the
// same id replaces it.
type session struct {
	id    string
	conn  *websocket.Conn
	since int64 // unix ms

	writeMu sync.Mutex // gorilla allows one concurrent writer

	mu      sync.Mutex
	pending map[string]chan *resFrame
	done    bool
}

func newSession(id string, conn *websocket.Conn) *session {
	return &session{id: id, conn: conn, since: time.Now().UnixMilli(), pending: map[string]chan *resFrame{}}
}

// writeWait bounds every socket write. A node that stops reading must not hold
// writeMu forever: the write fails, the session is closed, and waiting
// requests fail fast instead of outliving the request timeout.
var writeWait = 10 * time.Second

func (s *session) writeJSON(v any) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	_ = s.conn.SetWriteDeadline(time.Now().Add(writeWait))
	err := s.conn.WriteJSON(v)
	if err != nil {
		_ = s.conn.Close() // a timed-out gorilla writer is unusable; the read loop cleans up
	}
	return err
}

func (s *session) writeText(msg string) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	_ = s.conn.SetWriteDeadline(time.Now().Add(writeWait))
	err := s.conn.WriteMessage(websocket.TextMessage, []byte(msg))
	if err != nil {
		_ = s.conn.Close()
	}
	return err
}

// addPending registers a request and returns its channel; nil if the session is already gone.
func (s *session) addPending(rid string) chan *resFrame {
	s.mu.Lock()
	defer s.mu.Unlock()
	if s.done {
		return nil
	}
	ch := make(chan *resFrame, 1)
	s.pending[rid] = ch
	return ch
}

func (s *session) dropPending(rid string) {
	s.mu.Lock()
	delete(s.pending, rid)
	s.mu.Unlock()
}

// deliver hands a node's answer to the waiting request. Unknown rids are ignored.
func (s *session) deliver(f *resFrame) {
	s.mu.Lock()
	ch, ok := s.pending[f.Rid]
	if ok {
		delete(s.pending, f.Rid)
	}
	s.mu.Unlock()
	if ok {
		ch <- f
	}
}

// failAll resolves every waiting request with nil (the caller turns that into a 504)
// and marks the session finished.
func (s *session) failAll() {
	s.mu.Lock()
	s.done = true
	for rid, ch := range s.pending {
		delete(s.pending, rid)
		ch <- nil
	}
	s.mu.Unlock()
}

// Hub tracks live node sessions by id.
type Hub struct {
	mu    sync.Mutex
	nodes map[string]*session
}

func NewHub() *Hub { return &Hub{nodes: map[string]*session{}} }

func (h *Hub) get(id string) *session {
	h.mu.Lock()
	defer h.mu.Unlock()
	return h.nodes[id]
}

// register makes s the live session for its id and returns the one it replaced, if any.
func (h *Hub) register(s *session) *session {
	h.mu.Lock()
	defer h.mu.Unlock()
	old := h.nodes[s.id]
	h.nodes[s.id] = s
	return old
}

// remove drops s if it is still the live session; reports whether it was.
func (h *Hub) remove(s *session) bool {
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.nodes[s.id] == s {
		delete(h.nodes, s.id)
		return true
	}
	return false
}

func (h *Hub) liveCount() int {
	h.mu.Lock()
	defer h.mu.Unlock()
	return len(h.nodes)
}

// newRid is a random request id. A counter would repeat after a restart.
func newRid() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func mustJSON(v any) string {
	b, _ := json.Marshal(v)
	return string(b)
}
