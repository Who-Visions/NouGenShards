// nougen-supervisor keeps every NouGen account on this computer online.
//
// It runs with no window, starts when the user signs in, checks each
// account's node and tunnel every 30 seconds and restarts whatever stopped.
// It needs nothing installed: one file, no Python, no service manager.
//
//	nougen-supervisor run        watch the accounts (what autostart runs)
//	nougen-supervisor install    start at sign-in, and start now
//	nougen-supervisor uninstall  stop, and stop starting at sign-in
//	nougen-supervisor status     show every account (add -json for machines)
//	nougen-supervisor version
package main

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"sync"
	"syscall"
	"text/tabwriter"
	"time"
)

// version is stamped at build time: -ldflags "-X main.version=1.2.0".
var version = "dev"

const (
	defaultAddr = "127.0.0.1:47411"
	guardHeader = "X-NouGen-Supervisor"
)

// addr is where the control endpoint listens. It is always a loopback
// address: a wildcard or port-only value keeps its port and is pinned to
// 127.0.0.1, so the endpoint can never be reached from another computer.
func addr() string {
	a := os.Getenv("NOUGEN_SUPERVISOR_ADDR")
	if a == "" {
		return defaultAddr
	}
	host, port, err := net.SplitHostPort(a)
	if err != nil {
		return defaultAddr
	}
	if ip := net.ParseIP(host); ip == nil || !ip.IsLoopback() {
		host = "127.0.0.1"
	}
	return net.JoinHostPort(host, port)
}

// localHost reports whether a request's Host header names this computer on
// the port we listen on. A page that reaches us through a rebound DNS name
// carries its own host name here and is refused.
func localHost(host, listen string) bool {
	h, p, err := net.SplitHostPort(host)
	if err != nil {
		return false
	}
	_, want, _ := net.SplitHostPort(listen)
	if p != want {
		return false
	}
	if h == "localhost" {
		return true
	}
	ip := net.ParseIP(h)
	return ip != nil && ip.IsLoopback()
}

// rotatingFile is the supervisor's own log: one file capped at max bytes,
// with the previous one kept beside it.
type rotatingFile struct {
	mu   sync.Mutex
	path string
	max  int64
	f    *os.File
	size int64
}

func (r *rotatingFile) Write(p []byte) (int, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	if r.f == nil || r.size+int64(len(p)) > r.max {
		if r.f != nil {
			r.f.Close()
			_ = os.Remove(r.path + ".1")
			_ = os.Rename(r.path, r.path+".1")
		}
		f, err := os.OpenFile(r.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
		if err != nil {
			return 0, err
		}
		st, _ := f.Stat()
		r.f, r.size = f, st.Size()
	}
	n, err := r.f.Write(p)
	r.size += int64(n)
	return n, err
}

// handler serves the local control endpoint. Only this computer can reach
// it, and anything that changes state needs a header a web page cannot send
// across origins, so a site open in the browser cannot stop the nodes.
func handler(s *Supervisor, listen string, quit func()) http.Handler {
	mux := http.NewServeMux()
	mux.HandleFunc("/status", func(w http.ResponseWriter, r *http.Request) {
		if !localHost(r.Host, listen) {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(s.Snapshot())
	})
	mux.HandleFunc("/quit", func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost || !localHost(r.Host, listen) || r.Header.Get(guardHeader) != "1" {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		fmt.Fprintln(w, "stopping")
		go quit()
	})
	return mux
}

func fetchStatus(timeout time.Duration) (Status, error) {
	var st Status
	c := &http.Client{Timeout: timeout}
	resp, err := c.Get("http://" + addr() + "/status")
	if err != nil {
		return st, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return st, fmt.Errorf("status %d", resp.StatusCode)
	}
	err = json.NewDecoder(resp.Body).Decode(&st)
	return st, err
}

func requestQuit() error {
	req, _ := http.NewRequest(http.MethodPost, "http://"+addr()+"/quit", nil)
	req.Header.Set(guardHeader, "1")
	resp, err := (&http.Client{Timeout: 5 * time.Second}).Do(req)
	if err != nil {
		return err
	}
	resp.Body.Close()
	return nil
}

func cmdRun(base string) int {
	if err := os.MkdirAll(base, 0o700); err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	ln, err := net.Listen("tcp", addr())
	if err != nil {
		// The port doubles as the single-instance lock.
		if _, serr := fetchStatus(3 * time.Second); serr == nil {
			return 0 // already running
		}
		fmt.Fprintln(os.Stderr, "cannot listen on", addr(), err)
		return 1
	}
	log := slog.New(slog.NewJSONHandler(&rotatingFile{path: filepath.Join(base, "supervisor.log"), max: 2 << 20}, nil))
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	s := NewSupervisor(base, DefaultTiming(), realLauncher{base: base}, log)
	srv := &http.Server{Handler: handler(s, addr(), stop), ReadHeaderTimeout: 5 * time.Second}
	go func() {
		if err := srv.Serve(ln); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Error("control endpoint stopped", "err", err)
		}
	}()
	log.Info("supervisor started", "version", version, "base", base, "pid", os.Getpid())
	s.Run(ctx)
	log.Info("supervisor stopped", "version", version)
	shut, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	_ = srv.Shutdown(shut)
	return 0
}

func cmdInstall(base string, baseSet bool) int {
	self, err := os.Executable()
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		return 1
	}
	args := []string{"run"}
	if baseSet {
		args = append(args, "-base", base)
	}
	var ids []string
	for _, n := range Discover(base) {
		if n.Dir == base {
			ids = append(ids, "root") // the earliest layout registered itself as plain "NouGen"
			continue
		}
		ids = append(ids, n.ID)
	}
	if err := installAutostart(self, args, base, ids); err != nil {
		fmt.Fprintln(os.Stderr, "autostart:", err)
		return 1
	}
	// Replace a running older build, then start this one. A build that
	// answers is asked to quit; anything left (a build from before the
	// control endpoint, or one that did not quit in time) is ended, because
	// two supervisors would fight over the same ports.
	if st, err := fetchStatus(5 * time.Second); err != nil || st.Version != version {
		if err == nil {
			_ = requestQuit()
			for i := 0; i < 25; i++ {
				if _, err := fetchStatus(time.Second); err != nil {
					break
				}
				time.Sleep(200 * time.Millisecond)
			}
		}
		stopOthers()
		time.Sleep(300 * time.Millisecond)
	}
	if _, err := fetchStatus(5 * time.Second); err != nil {
		if err := startDetached(self, args); err != nil {
			fmt.Fprintln(os.Stderr, "start:", err)
			return 1
		}
	}
	for i := 0; i < 50; i++ {
		if _, err := fetchStatus(time.Second); err == nil {
			fmt.Println("installed: running, and starts at sign-in")
			return 0
		}
		time.Sleep(200 * time.Millisecond)
	}
	fmt.Fprintln(os.Stderr, "installed, but it did not start; see supervisor.log in", base)
	return 1
}

func cmdUninstall() int {
	err := removeAutostart()
	_ = requestQuit()
	if err != nil {
		fmt.Fprintln(os.Stderr, "autostart:", err)
		return 1
	}
	fmt.Println("uninstalled: stopped, and no longer starts at sign-in (nodes already running were left on)")
	return 0
}

func cmdStatus(out io.Writer, asJSON bool) int {
	st, err := fetchStatus(5 * time.Second)
	auto := "off"
	if autostartOn() {
		auto = "on"
	}
	if err != nil {
		if asJSON {
			fmt.Fprintf(out, "{\"running\":false,\"autostart\":%q}\n", auto)
		} else {
			fmt.Fprintf(out, "supervisor: not running   autostart: %s\n", auto)
		}
		return 1
	}
	bad := 0
	for _, n := range st.Nodes {
		if n.Node.State != "up" || (n.Tunnel.State != "up" && n.Tunnel.State != "none") {
			bad++
		}
	}
	if asJSON {
		_ = json.NewEncoder(out).Encode(struct {
			Running   bool   `json:"running"`
			Autostart string `json:"autostart"`
			Status
		}{true, auto, st})
		if bad > 0 {
			return 2
		}
		return 0
	}
	fmt.Fprintf(out, "supervisor: running %s   autostart: %s\n", st.Version, auto)
	tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
	fmt.Fprintln(tw, "ACCOUNT\tPORT\tNODE\tTUNNEL\tSTARTS\tADDRESS")
	for _, n := range st.Nodes {
		fmt.Fprintf(tw, "%s\t%d\t%s\t%s\t%d/%d\t%s\n", n.ID, n.Port, n.Node.State, n.Tunnel.State, n.Node.Starts, n.Tunnel.Starts, n.URL)
	}
	tw.Flush()
	if len(st.Nodes) == 0 {
		fmt.Fprintln(out, "no accounts are set up on this computer yet")
	}
	if bad > 0 {
		return 2
	}
	return 0
}

func main() {
	attachConsole()
	cmd := "run"
	args := os.Args[1:]
	if len(args) > 0 && args[0] != "" && args[0][0] != '-' {
		cmd, args = args[0], args[1:]
	}
	fs := flag.NewFlagSet(cmd, flag.ExitOnError)
	base := fs.String("base", "", "folder that holds the account folders (default: the join setup's folder)")
	asJSON := fs.Bool("json", false, "status: print JSON")
	_ = fs.Parse(args)
	baseSet := *base != ""
	if !baseSet {
		*base = DefaultBase()
	}
	code := 0
	switch cmd {
	case "run":
		code = cmdRun(*base)
	case "install":
		code = cmdInstall(*base, baseSet)
	case "uninstall":
		code = cmdUninstall()
	case "status":
		code = cmdStatus(os.Stdout, *asJSON)
	case "version":
		fmt.Println(version)
	default:
		fmt.Fprintln(os.Stderr, "usage: nougen-supervisor [run|install|uninstall|status|version] [-base DIR] [-json]")
		code = 64
	}
	os.Exit(code)
}
