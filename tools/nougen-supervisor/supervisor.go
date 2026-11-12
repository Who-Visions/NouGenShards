package main

import (
	"context"
	"fmt"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"sync"
	"time"
)

// Timing holds every interval the supervisor uses, so tests can shrink them.
type Timing struct {
	Tick        time.Duration // how often every node is checked
	NodeGrace   time.Duration // how long a started node may take to answer (first start downloads Python)
	TunnelGrace time.Duration // how long a started tunnel may take to connect
	BackoffMin  time.Duration // wait before the first restart
	BackoffMax  time.Duration // longest wait between restarts
	Stable      time.Duration // healthy this long resets the wait to BackoffMin
	Probe       time.Duration // timeout of one health request
	Fails       int           // failed checks in a row before starting a node this program did not start
}

// DefaultTiming is what runs on a real computer.
func DefaultTiming() Timing {
	return Timing{
		Tick: 30 * time.Second, NodeGrace: 8 * time.Minute, TunnelGrace: 2 * time.Minute,
		BackoffMin: 5 * time.Second, BackoffMax: 5 * time.Minute, Stable: 2 * time.Minute,
		Probe: 4 * time.Second, Fails: 2,
	}
}

// Launcher builds the commands the supervisor runs. Tests swap it out.
type Launcher interface {
	Node(n Node) *exec.Cmd
	Tunnel(n Node, metricsAddr string) *exec.Cmd
}

// realLauncher runs the node and tunnel the same way the join setup does.
type realLauncher struct{ base string }

func exe(name string) string {
	if runtime.GOOS == "windows" {
		return name + ".exe"
	}
	return name
}

func (l realLauncher) Node(n Node) *exec.Cmd {
	cmd := exec.Command(filepath.Join(l.base, exe("uv")), "run", "--python", "3.11", filepath.Join(n.SrcDir(), "app.py"))
	cmd.Dir = n.SrcDir()
	cmd.Env = append(os.Environ(),
		"NGS_NODE_TOKEN="+n.Token, "NGS_HUD_USER="+n.ID, "NGS_HUD_PASSWORD="+n.Token,
		fmt.Sprintf("NGS_PORT=%d", n.Port),
		"NOUGEN_VAULT_DIR="+filepath.Join(n.Dir, "shards"), "NOUGEN_HOME="+n.Dir)
	return cmd
}

func (l realLauncher) Tunnel(n Node, metricsAddr string) *exec.Cmd {
	// The token goes in the environment, not the arguments: arguments are
	// visible to every other program on the computer.
	cmd := exec.Command(filepath.Join(n.Dir, exe("cloudflared")), "tunnel", "--no-autoupdate", "--metrics", metricsAddr, "run")
	cmd.Dir = n.Dir
	cmd.Env = append(os.Environ(), "TUNNEL_TOKEN="+n.Tunnel)
	return cmd
}

// proc is one running child. done is closed when it exits, which is the only
// thing other goroutines ever read, so there is no shared flag to race on.
type proc struct {
	cmd     *exec.Cmd
	done    chan struct{}
	started time.Time
}

func (p *proc) alive() bool {
	if p == nil {
		return false
	}
	select {
	case <-p.done:
		return false
	default:
		return true
	}
}

// startProc runs cmd with its output appended to logPath. The log file is
// closed when the child exits, so restarts never leak a handle.
func startProc(cmd *exec.Cmd, logPath string, now time.Time) (*proc, error) {
	if st, err := os.Stat(logPath); err == nil && st.Size() > 5<<20 {
		_ = os.Remove(logPath + ".1")
		_ = os.Rename(logPath, logPath+".1")
	}
	logf, err := os.OpenFile(logPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return nil, err
	}
	cmd.Stdout, cmd.Stderr = logf, logf
	hideAndGroup(cmd)
	if err := cmd.Start(); err != nil {
		logf.Close()
		return nil, err
	}
	p := &proc{cmd: cmd, done: make(chan struct{}), started: now}
	go func() {
		_ = cmd.Wait()
		logf.Close()
		close(p.done)
	}()
	return p, nil
}

// unit is one supervised thing: a node or a tunnel.
type unit struct {
	proc      *proc
	state     string
	fails     int
	restarts  int
	backoff   time.Duration
	nextStart time.Time
	upSince   time.Time
	lastOK    time.Time
	lastErr   string
}

type entry struct {
	node   Node
	n, tun unit
}

// Supervisor keeps every account's node and tunnel running.
type Supervisor struct {
	Base   string
	T      Timing
	L      Launcher
	Log    *slog.Logger
	client *http.Client

	mu      sync.Mutex
	entries map[string]*entry
	started time.Time
}

// NewSupervisor builds a supervisor over the accounts under base.
func NewSupervisor(base string, t Timing, l Launcher, log *slog.Logger) *Supervisor {
	return &Supervisor{Base: base, T: t, L: l, Log: log,
		client:  &http.Client{Timeout: t.Probe},
		entries: map[string]*entry{}, started: time.Now()}
}

func (s *Supervisor) ok(url string) bool {
	resp, err := s.client.Get(url)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == http.StatusOK
}

func portOpen(port int, timeout time.Duration) bool {
	c, err := net.DialTimeout("tcp", fmt.Sprintf("127.0.0.1:%d", port), timeout)
	if err != nil {
		return false
	}
	c.Close()
	return true
}

// metricsAddr is where an account's tunnel reports readiness. It is derived
// from the node port so two accounts never collide.
func metricsAddr(port int) string { return fmt.Sprintf("127.0.0.1:%d", 20000+port%40000) }

func (s *Supervisor) bump(u *unit, now time.Time) {
	if u.backoff < s.T.BackoffMin {
		u.backoff = s.T.BackoffMin
	}
	u.nextStart = now.Add(u.backoff)
	u.backoff *= 2
	if u.backoff > s.T.BackoffMax {
		u.backoff = s.T.BackoffMax
	}
}

func (s *Supervisor) markUp(u *unit, now time.Time) {
	if u.state != "up" {
		u.upSince = now
	}
	u.state, u.fails, u.lastOK, u.lastErr = "up", 0, now, ""
	if now.Sub(u.upSince) >= s.T.Stable {
		u.backoff = s.T.BackoffMin
	}
}

func (s *Supervisor) launch(u *unit, cmd *exec.Cmd, logPath, id, kind string, now time.Time) {
	p, err := startProc(cmd, logPath, now)
	s.bump(u, now)
	if err != nil {
		u.state, u.lastErr = "failed", err.Error()
		s.Log.Error("start failed", "account", id, "what", kind, "err", err)
		return
	}
	u.proc, u.state = p, "starting"
	u.restarts++
	s.Log.Info("started", "account", id, "what", kind, "pid", p.cmd.Process.Pid, "starts", u.restarts)
}

func (s *Supervisor) checkNode(e *entry, now time.Time) {
	u, n := &e.n, e.node
	if s.ok(fmt.Sprintf("http://127.0.0.1:%d/health", n.Port)) {
		s.markUp(u, now)
		return
	}
	u.fails++
	if u.proc.alive() {
		if now.Sub(u.proc.started) < s.T.NodeGrace {
			u.state = "starting"
			return
		}
		s.Log.Warn("not answering, stopping it", "account", n.ID, "what", "node", "pid", u.proc.cmd.Process.Pid)
		killTree(u.proc.cmd)
		u.state = "restarting"
		return
	}
	// Nothing of ours is running. A node started by something else gets
	// T.Fails checks before we step in, so one slow answer does not start a
	// second copy on the same port.
	if u.proc == nil && u.fails < s.T.Fails {
		u.state = "down"
		return
	}
	if now.Before(u.nextStart) {
		u.state = "waiting"
		return
	}
	if portOpen(n.Port, s.T.Probe) {
		u.state, u.lastErr = "port-busy", "another program is using this port and is not a healthy node"
		s.bump(u, now)
		s.Log.Error("port busy", "account", n.ID, "port", n.Port)
		return
	}
	s.launch(u, s.L.Node(n), filepath.Join(n.Dir, "node.log"), n.ID, "node", now)
}

func (s *Supervisor) checkTunnel(e *entry, now time.Time) {
	u, n := &e.tun, e.node
	if n.Tunnel == "" {
		u.state = "none"
		return
	}
	addr := metricsAddr(n.Port)
	if u.proc.alive() {
		if s.ok("http://" + addr + "/ready") {
			s.markUp(u, now)
			return
		}
		u.fails++
		if now.Sub(u.proc.started) < s.T.TunnelGrace {
			u.state = "starting"
			return
		}
		s.Log.Warn("not connected, stopping it", "account", n.ID, "what", "tunnel", "pid", u.proc.cmd.Process.Pid)
		killTree(u.proc.cmd)
		u.state = "restarting"
		return
	}
	if now.Before(u.nextStart) {
		u.state = "waiting"
		return
	}
	// A tunnel may have several connectors, so starting ours beside one left
	// by an older launcher is harmless; the old one is gone after a restart.
	s.launch(u, s.L.Tunnel(n, addr), filepath.Join(n.Dir, "tunnel.log"), n.ID, "tunnel", now)
}

// Tick checks every account once. New account folders are picked up here, so
// a second person can join on a running computer without restarting anything.
func (s *Supervisor) Tick(now time.Time) {
	s.mu.Lock()
	defer s.mu.Unlock()
	seen := map[string]bool{}
	for _, n := range Discover(s.Base) {
		seen[n.ID] = true
		e := s.entries[n.ID]
		if e == nil {
			e = &entry{}
			s.entries[n.ID] = e
			s.Log.Info("watching", "account", n.ID, "port", n.Port, "from", n.Source)
		}
		e.node = n
		func() {
			defer func() {
				if r := recover(); r != nil {
					s.Log.Error("check failed", "account", n.ID, "err", fmt.Sprint(r))
				}
			}()
			s.checkNode(e, now)
			s.checkTunnel(e, now)
		}()
	}
	for id, e := range s.entries {
		if !seen[id] {
			s.Log.Info("account removed, stopping it", "account", id)
			if e.n.proc.alive() {
				killTree(e.n.proc.cmd)
			}
			if e.tun.proc.alive() {
				killTree(e.tun.proc.cmd)
			}
			delete(s.entries, id)
		}
	}
}

// Run checks on every tick until ctx ends. Children are left running on exit:
// stopping the watcher must not take the nodes down with it.
func (s *Supervisor) Run(ctx context.Context) {
	t := time.NewTicker(s.T.Tick)
	defer t.Stop()
	s.Tick(time.Now())
	for {
		select {
		case <-ctx.Done():
			return
		case now := <-t.C:
			s.Tick(now)
		}
	}
}

// UnitStatus and the types below are the public shape of /status. They carry
// no token and no tunnel credential.
type UnitStatus struct {
	State   string `json:"state"`
	Starts  int    `json:"starts"`
	PID     int    `json:"pid,omitempty"`
	LastOK  string `json:"last_ok,omitempty"`
	LastErr string `json:"last_error,omitempty"`
}

type NodeStatus struct {
	ID     string     `json:"id"`
	Port   int        `json:"port"`
	URL    string     `json:"url,omitempty"`
	Source string     `json:"source"`
	Node   UnitStatus `json:"node"`
	Tunnel UnitStatus `json:"tunnel"`
}

type Status struct {
	Version string       `json:"version"`
	Base    string       `json:"base"`
	Started string       `json:"started"`
	Nodes   []NodeStatus `json:"nodes"`
}

func unitStatus(u *unit) UnitStatus {
	st := UnitStatus{State: u.state, Starts: u.restarts, LastErr: u.lastErr}
	if u.proc.alive() {
		st.PID = u.proc.cmd.Process.Pid
	}
	if !u.lastOK.IsZero() {
		st.LastOK = u.lastOK.UTC().Format(time.RFC3339)
	}
	return st
}

// Snapshot reports what the supervisor currently believes.
func (s *Supervisor) Snapshot() Status {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := Status{Version: version, Base: s.Base, Started: s.started.UTC().Format(time.RFC3339), Nodes: []NodeStatus{}}
	for _, n := range Discover(s.Base) {
		e := s.entries[n.ID]
		if e == nil {
			continue
		}
		out.Nodes = append(out.Nodes, NodeStatus{ID: n.ID, Port: n.Port, URL: n.URL, Source: n.Source,
			Node: unitStatus(&e.n), Tunnel: unitStatus(&e.tun)})
	}
	return out
}
