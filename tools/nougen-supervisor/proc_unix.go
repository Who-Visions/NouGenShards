//go:build !windows

package main

import (
	"fmt"
	"html"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strconv"
	"strings"
	"syscall"
)

const (
	agentLabel = "com.nougen.supervisor"
	cronMark   = "# nougen-supervisor"
)

// hideAndGroup puts a child in its own process group so it can be stopped
// together with everything it started.
func hideAndGroup(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}
}

// track has nothing to add on Unix: the process group set at start is the group.
func track(cmd *exec.Cmd) uintptr { return 0 }

// killGroup stops a child and everything it started. It signals the group
// only while the child is still running: a group id is only certain to be
// ours while its leader exists.
func killGroup(p *proc) {
	if p == nil || p.cmd == nil || p.cmd.Process == nil || !p.alive() {
		return
	}
	if syscall.Kill(-p.cmd.Process.Pid, syscall.SIGKILL) != nil {
		_ = p.cmd.Process.Kill()
	}
}

func closeGroup(p *proc) {}

// portOwner finds the program listening on a local port and its command line.
func portOwner(port int) (int, string) {
	pid := 0
	if out, err := exec.Command("lsof", "-nP", "-iTCP:"+strconv.Itoa(port), "-sTCP:LISTEN", "-t").Output(); err == nil {
		if f := strings.Fields(string(out)); len(f) > 0 {
			pid, _ = strconv.Atoi(f[0])
		}
	}
	if pid == 0 { // no lsof: Linux always has ss
		out, _ := exec.Command("ss", "-ltnpH", "sport", "=", ":"+strconv.Itoa(port)).Output()
		if i := strings.Index(string(out), "pid="); i >= 0 {
			rest := string(out)[i+4:]
			if j := strings.IndexAny(rest, ",)"); j > 0 {
				pid, _ = strconv.Atoi(rest[:j])
			}
		}
	}
	if pid <= 1 {
		return 0, ""
	}
	cl, _ := exec.Command("ps", "-o", "command=", "-p", strconv.Itoa(pid)).Output()
	return pid, strings.TrimSpace(string(cl))
}

// killPID stops a program this supervisor did not start. Callers confirm
// what the id belongs to immediately before calling.
func killPID(pid int) {
	_ = syscall.Kill(pid, syscall.SIGKILL)
}

func agentPath() string {
	home, _ := os.UserHomeDir()
	return filepath.Join(home, "Library", "LaunchAgents", agentLabel+".plist")
}

func shQuote(s string) string { return "'" + strings.ReplaceAll(s, "'", `'\''`) + "'" }

func crontab() string {
	out, _ := exec.Command("crontab", "-l").Output()
	return string(out)
}

func writeCrontab(keep func(line string) bool, add string) error {
	var lines []string
	for _, l := range strings.Split(crontab(), "\n") {
		if l != "" && keep(l) {
			lines = append(lines, l)
		}
	}
	if add != "" {
		lines = append(lines, add)
	}
	cmd := exec.Command("crontab", "-")
	cmd.Stdin = strings.NewReader(strings.Join(lines, "\n") + "\n")
	return cmd.Run()
}

func installAutostart(self string, args []string, base string, ids []string) error {
	if runtime.GOOS == "darwin" {
		var b strings.Builder
		b.WriteString(`<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>Label</key><string>` + agentLabel + `</string><key>ProgramArguments</key><array>`)
		for _, a := range append([]string{self}, args...) {
			b.WriteString("<string>" + html.EscapeString(a) + "</string>")
		}
		b.WriteString(`</array><key>RunAtLoad</key><true/></dict></plist>`)
		if err := os.MkdirAll(filepath.Dir(agentPath()), 0o755); err != nil {
			return err
		}
		if err := os.WriteFile(agentPath(), []byte(b.String()), 0o644); err != nil {
			return err
		}
		// Older setups registered one launcher per account. Unload each
		// before removing its file, or launchd keeps the job until reboot.
		for _, id := range ids {
			old := filepath.Join(filepath.Dir(agentPath()), "com.nougen.node."+id+".plist")
			if _, err := os.Stat(old); err == nil {
				_ = exec.Command("launchctl", "unload", old).Run()
				_ = os.Remove(old)
			}
		}
		return nil
	}
	line := "@reboot " + shQuote(self)
	for _, a := range args {
		line += " " + shQuote(a)
	}
	line += " >/dev/null 2>&1 " + cronMark
	return writeCrontab(func(l string) bool {
		// Drop our old line and the per-account run.sh lines older setups added.
		return !strings.Contains(l, cronMark) && !(strings.Contains(l, base) && strings.Contains(l, "run.sh"))
	}, line)
}

func removeAutostart() error {
	if runtime.GOOS == "darwin" {
		err := os.Remove(agentPath())
		if os.IsNotExist(err) {
			return nil
		}
		return err
	}
	if !autostartOn() {
		return nil
	}
	return writeCrontab(func(l string) bool { return !strings.Contains(l, cronMark) }, "")
}

func autostartOn() bool {
	if runtime.GOOS == "darwin" {
		_, err := os.Stat(agentPath())
		return err == nil
	}
	return strings.Contains(crontab(), cronMark)
}

// stopOthers ends every other supervisor process started from the same file.
// The match is on the full path: the kernel truncates process names to 15
// characters, so matching the bare name "nougen-supervisor" would find nothing.
func stopOthers() {
	self, err := os.Executable()
	if err != nil {
		return
	}
	out, _ := exec.Command("pgrep", "-f", self).Output()
	for _, f := range strings.Fields(string(out)) {
		if pid, _ := strconv.Atoi(f); pid > 1 && pid != os.Getpid() {
			_ = syscall.Kill(pid, syscall.SIGTERM)
		}
	}
}

func startDetached(self string, args []string) error {
	cmd := exec.Command(self, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start: %w", err)
	}
	return cmd.Process.Release()
}

func attachConsole() {}
