//go:build !windows

package main

import (
	"fmt"
	"html"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
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

// killTree stops a child and everything it started.
func killTree(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	if syscall.Kill(-cmd.Process.Pid, syscall.SIGKILL) != nil {
		_ = cmd.Process.Kill()
	}
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
		// Older setups registered one launcher per account.
		for _, id := range ids {
			_ = os.Remove(filepath.Join(filepath.Dir(agentPath()), "com.nougen.node."+id+".plist"))
		}
		return nil
	}
	line := "@reboot " + shQuote(self)
	for _, a := range args {
		line += " " + shQuote(a)
	}
	line += " >/dev/null 2>&1 " + cronMark
	legacy := filepath.Join(base, "")
	return writeCrontab(func(l string) bool {
		// Drop our old line and the per-account run.sh lines older setups added.
		return !strings.Contains(l, cronMark) && !(strings.Contains(l, legacy) && strings.Contains(l, "run.sh"))
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

func startDetached(self string, args []string) error {
	cmd := exec.Command(self, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{Setsid: true}
	if err := cmd.Start(); err != nil {
		return fmt.Errorf("start: %w", err)
	}
	return cmd.Process.Release()
}

func attachConsole() {}
