//go:build windows

// nougen-supervisor keeps every NouGen tenant node on this Windows computer running.
// No console window (build with -ldflags "-H=windowsgui"), no Claude, no Python needed for itself.
//
// Each node is described by the run.ps1 the join setup wrote:
//
//	%LOCALAPPDATA%\NouGen\run.ps1           (older single install; works in NouGen\NouGenShards)
//	%LOCALAPPDATA%\NouGen\<handle>\run.ps1  (one folder per account)
//
// plus an optional public.txt next to it holding the node's https URL.
// Every 30 s it re-reads those files (new accounts are picked up live) and, for each node:
//   - local /health down           -> (re)start `uv run --python 3.11 app.py` with that node's env
//   - local up, public URL not 200 -> (re)start that node's cloudflared tunnel
//
// Restarts back off exponentially so a broken node cannot spin. A hung node or a tunnel that is
// running but not serving is killed as a whole process tree and started again.
// Children start hidden (CREATE_NO_WINDOW). One instance at a time: it holds 127.0.0.1:4499,
// which also serves GET /status (JSON, no secrets).
// Log: %LOCALAPPDATA%\NouGen\supervisor.log
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	interval     = 30 * time.Second
	startGrace   = 240 * time.Second // first start may download Python
	cfGrace      = 60 * time.Second
	maxBackoff   = 30 * time.Minute
	stuckTunnel  = 6                       // consecutive public failures (~3 min) before a live tunnel is recycled
	noWindow     = 0x08000000 | 0x00000200 // CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
	lockAddr     = "127.0.0.1:4499"
	utf8BOM      = "\xef\xbb\xbf"
	logMaxBytes  = 2_000_000
	localTimeout = 4 * time.Second
)

// version is stamped at build time: -ldflags "-X main.version=<v>".
var version = "dev"

var (
	home     = filepath.Join(os.Getenv("LOCALAPPDATA"), "NouGen")
	reEnv    = regexp.MustCompile(`\$env:(\w+)\s*=\s*'([^']*)'`)
	reTunnel = regexp.MustCompile(`'--token'\s*,\s*'([^']+)'`)
	client   = &http.Client{Timeout: 8 * time.Second}
	local    = &http.Client{Timeout: localTimeout}
	logger   = slog.New(slog.NewTextHandler(io.Discard, nil))
)

// proc is a child we started. done is closed by the reaper goroutine when the child exits,
// so liveness is read through a channel instead of racing on exec.Cmd.ProcessState.
type proc struct {
	cmd  *exec.Cmd
	done chan struct{}
}

func alive(p *proc) bool {
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

func pid(p *proc) int {
	if !alive(p) || p.cmd == nil || p.cmd.Process == nil {
		return 0
	}
	return p.cmd.Process.Pid
}

type node struct {
	// configuration, re-read every tick
	name, dir, work, cloudflared, tunnel, public string
	port                                         int
	env                                          map[string]string
	// runtime
	app, cf               *proc
	appStarted, cfStarted time.Time
	appFails, cfFails     int // consecutive starts that did not lead to a healthy check
	pubFails              int // consecutive public failures while local is up
	restarts              int
	localUp, publicUp     bool
}

// rotatingFile is an io.Writer that appends to path and rotates it to path+".1" past maxBytes.
// The file is opened per write so the log can be moved or deleted while the supervisor runs.
type rotatingFile struct {
	path     string
	maxBytes int64
}

func (r rotatingFile) Write(p []byte) (int, error) {
	if fi, err := os.Stat(r.path); err == nil && fi.Size() > r.maxBytes {
		_ = os.Rename(r.path, r.path+".1")
	}
	f, err := os.OpenFile(r.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if err != nil {
		return 0, err
	}
	defer f.Close()
	return f.Write(p)
}

// backoff returns base doubled once per consecutive failure, capped at max.
func backoff(base time.Duration, fails int, max time.Duration) time.Duration {
	d := base
	for i := 0; i < fails && d < max; i++ {
		d *= 2
	}
	if d > max {
		d = max
	}
	return d
}

func parseRun(path string) *node {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	text := strings.TrimPrefix(string(b), utf8BOM)
	env := map[string]string{}
	for _, m := range reEnv.FindAllStringSubmatch(text, -1) {
		env[m[1]] = m[2]
	}
	tm := reTunnel.FindStringSubmatch(text)
	port, err := strconv.Atoi(env["NGS_PORT"])
	if err != nil || tm == nil {
		return nil
	}
	dir := filepath.Dir(path)
	if strings.Contains(text, "NOUGEN_VAULT_DIR") && strings.Contains(text, "Join-Path $t 'shards'") {
		env["NOUGEN_VAULT_DIR"] = filepath.Join(dir, "shards")
		env["NOUGEN_HOME"] = dir
	}
	n := &node{name: filepath.Base(dir), dir: dir, work: filepath.Join(dir, "NouGenShards"), tunnel: tm[1], port: port, env: env}
	if strings.EqualFold(dir, home) {
		n.name = "root"
	}
	n.cloudflared = filepath.Join(dir, "cloudflared.exe")
	if _, err := os.Stat(n.cloudflared); err != nil {
		n.cloudflared = filepath.Join(home, "cloudflared.exe")
	}
	if pb, err := os.ReadFile(filepath.Join(dir, "public.txt")); err == nil {
		n.public = strings.TrimRight(strings.TrimSpace(strings.TrimPrefix(string(pb), utf8BOM)), "/")
	}
	if _, err := os.Stat(n.work); err != nil {
		return nil
	}
	return n
}

func discover() []*node {
	paths := []string{filepath.Join(home, "run.ps1")}
	more, _ := filepath.Glob(filepath.Join(home, "*", "run.ps1"))
	sort.Strings(more)
	paths = append(paths, more...)
	var out []*node
	for _, p := range paths {
		if n := parseRun(p); n != nil {
			out = append(out, n)
		}
	}
	return out
}

// refresh merges a fresh discovery into the current set: configuration is replaced, runtime
// state (child handles, counters) is kept, new folders are added, removed folders are dropped
// (their processes are left alone).
func refresh(cur []*node) []*node {
	byDir := make(map[string]*node, len(cur))
	for _, n := range cur {
		byDir[strings.ToLower(n.dir)] = n
	}
	fresh := discover()
	out := make([]*node, 0, len(fresh))
	for _, f := range fresh {
		key := strings.ToLower(f.dir)
		if old, ok := byDir[key]; ok {
			old.name, old.work, old.cloudflared, old.tunnel = f.name, f.work, f.cloudflared, f.tunnel
			old.public, old.port, old.env = f.public, f.port, f.env
			out = append(out, old)
			delete(byDir, key)
		} else {
			logger.Info("node added", "node", f.name, "port", f.port)
			out = append(out, f)
		}
	}
	for _, gone := range byDir {
		logger.Info("node removed from watch", "node", gone.name)
	}
	return out
}

func ok(c *http.Client, url string) bool {
	resp, err := c.Get(url)
	if err != nil {
		return false
	}
	resp.Body.Close()
	return resp.StatusCode == 200
}

func launch(name string, args []string, dir string, env []string, logFile string) (*proc, error) {
	c := exec.Command(name, args...)
	c.Dir = dir
	if env != nil {
		c.Env = env
	}
	f, ferr := os.OpenFile(logFile, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o644)
	if ferr == nil {
		c.Stdout, c.Stderr = f, f
	}
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: noWindow}
	if err := c.Start(); err != nil {
		if f != nil {
			f.Close()
		}
		return nil, err
	}
	p := &proc{cmd: c, done: make(chan struct{})}
	go func() { // reap the child, then release its log handle
		_ = c.Wait()
		if f != nil {
			f.Close()
		}
		close(p.done)
	}()
	return p, nil
}

// killTree ends a child and everything it started (uv -> python), so the port is really freed.
func killTree(p *proc) {
	id := pid(p)
	if id == 0 {
		return
	}
	c := exec.Command("taskkill", "/T", "/F", "/PID", strconv.Itoa(id))
	c.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: noWindow}
	_ = c.Run()
	select {
	case <-p.done:
	case <-time.After(5 * time.Second):
	}
}

func startApp(n *node) {
	env := os.Environ()
	for k, v := range n.env {
		env = append(env, k+"="+v)
	}
	p, err := launch(filepath.Join(home, "uv.exe"), []string{"run", "--python", "3.11", "app.py"},
		n.work, env, filepath.Join(n.dir, "node.log"))
	n.appStarted = time.Now()
	n.appFails++
	n.restarts++
	if err != nil {
		logger.Error("node start failed", "node", n.name, "err", err)
		return
	}
	n.app = p
	logger.Info("started node", "node", n.name, "port", n.port, "pid", p.cmd.Process.Pid, "attempt", n.appFails)
}

func startTunnel(n *node) {
	p, err := launch(n.cloudflared, []string{"tunnel", "--no-autoupdate", "run", "--token", n.tunnel},
		n.dir, nil, filepath.Join(n.dir, "tunnel.log"))
	n.cfStarted = time.Now()
	n.cfFails++
	n.restarts++
	if err != nil {
		logger.Error("tunnel start failed", "node", n.name, "err", err)
		return
	}
	n.cf = p
	logger.Info("started tunnel", "node", n.name, "pid", p.cmd.Process.Pid, "attempt", n.cfFails)
}

func tick(nodes []*node) {
	for _, n := range nodes {
		n.localUp = ok(local, fmt.Sprintf("http://127.0.0.1:%d/health", n.port))
		if n.localUp {
			n.appFails = 0
		} else if time.Since(n.appStarted) > backoff(startGrace, n.appFails-1, maxBackoff) {
			if alive(n.app) {
				logger.Warn("node running but /health failing; restarting", "node", n.name)
				killTree(n.app)
			}
			startApp(n)
		}

		if !n.localUp || n.public == "" {
			n.publicUp = false
			continue
		}
		n.publicUp = ok(client, n.public+"/health")
		if n.publicUp {
			n.pubFails, n.cfFails = 0, 0
			continue
		}
		n.pubFails++
		wait := backoff(cfGrace, n.cfFails-1, maxBackoff)
		switch {
		case !alive(n.cf) && time.Since(n.cfStarted) > wait:
			startTunnel(n)
		case alive(n.cf) && n.pubFails >= stuckTunnel && time.Since(n.cfStarted) > wait:
			logger.Warn("tunnel running but public URL failing; recycling", "node", n.name)
			killTree(n.cf)
			startTunnel(n)
			n.pubFails = 0
		}
	}
}

// ---- status (served on the lock port; never includes tokens or env) ----

type nodeStatus struct {
	Name      string `json:"name"`
	Port      int    `json:"port"`
	Public    string `json:"public"`
	LocalUp   bool   `json:"local_up"`
	PublicUp  bool   `json:"public_up"`
	AppPID    int    `json:"app_pid"`
	TunnelPID int    `json:"tunnel_pid"`
	Restarts  int    `json:"restarts"`
}

type status struct {
	Version   string       `json:"version"`
	Started   time.Time    `json:"started"`
	LastCheck time.Time    `json:"last_check"`
	Nodes     []nodeStatus `json:"nodes"`
}

var (
	snapMu sync.RWMutex
	snap   status
)

func publish(started time.Time, nodes []*node) {
	s := status{Version: version, Started: started, LastCheck: time.Now(), Nodes: make([]nodeStatus, 0, len(nodes))}
	for _, n := range nodes {
		s.Nodes = append(s.Nodes, nodeStatus{n.name, n.port, n.public, n.localUp, n.publicUp, pid(n.app), pid(n.cf), n.restarts})
	}
	snapMu.Lock()
	snap = s
	snapMu.Unlock()
}

func statusHandler(w http.ResponseWriter, _ *http.Request) {
	snapMu.RLock()
	s := snap
	snapMu.RUnlock()
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(s)
}

func main() {
	l, err := net.Listen("tcp", lockAddr)
	if err != nil {
		return // another supervisor is already running
	}
	defer l.Close()
	logger = slog.New(slog.NewTextHandler(rotatingFile{path: filepath.Join(home, "supervisor.log"), maxBytes: logMaxBytes}, nil))

	started := time.Now()
	mux := http.NewServeMux()
	mux.HandleFunc("/status", statusHandler)
	go func() { _ = http.Serve(l, mux) }()

	nodes := refresh(nil)
	logger.Info("go supervisor up", "version", version, "nodes", len(nodes))
	tk := time.NewTicker(interval)
	defer tk.Stop()
	for {
		func() {
			defer func() {
				if r := recover(); r != nil {
					logger.Error("tick panic", "err", r)
				}
			}()
			nodes = refresh(nodes)
			tick(nodes)
			publish(started, nodes)
		}()
		<-tk.C
	}
}
