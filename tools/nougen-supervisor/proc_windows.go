//go:build windows

package main

import (
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
)

const (
	createNoWindow        = 0x08000000
	createNewProcessGroup = 0x00000200
	runKey                = `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
	runName               = "NouGen-Supervisor"
)

// hideAndGroup makes sure a child never opens a window.
func hideAndGroup(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow | createNewProcessGroup}
}

func hidden(name string, args ...string) *exec.Cmd {
	cmd := exec.Command(name, args...)
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
	return cmd
}

// killTree stops a child and everything it started. `uv run` starts Python
// as its own child, so killing only uv would leave the node holding its port.
func killTree(cmd *exec.Cmd) {
	if cmd == nil || cmd.Process == nil {
		return
	}
	if hidden("taskkill", "/T", "/F", "/PID", strconv.Itoa(cmd.Process.Pid)).Run() != nil {
		_ = cmd.Process.Kill()
	}
}

func quoteArg(s string) string {
	if s != "" && !strings.ContainsAny(s, " \t\"") {
		return s
	}
	return `"` + strings.ReplaceAll(s, `"`, `\"`) + `"`
}

func installAutostart(self string, args []string, base string, ids []string) error {
	line := `"` + self + `"`
	for _, a := range args {
		line += " " + quoteArg(a)
	}
	if err := hidden("reg", "add", runKey, "/v", runName, "/t", "REG_SZ", "/d", line, "/f").Run(); err != nil {
		return err
	}
	// Older setups registered one launcher per account. Left in place they
	// would race this program at sign-in for the same ports.
	for _, id := range ids {
		_ = hidden("reg", "delete", runKey, "/v", "NouGen-"+id, "/f").Run()
	}
	return nil
}

func removeAutostart() error {
	if !autostartOn() {
		return nil
	}
	return hidden("reg", "delete", runKey, "/v", runName, "/f").Run()
}

func autostartOn() bool {
	return hidden("reg", "query", runKey, "/v", runName).Run() == nil
}

func startDetached(self string, args []string) error {
	cmd := hidden(self, args...)
	cmd.SysProcAttr.CreationFlags |= createNewProcessGroup
	if err := cmd.Start(); err != nil {
		return err
	}
	return cmd.Process.Release()
}

// attachConsole lets `status` print when run from a terminal. The program is
// built without a console so it never flashes a window at sign-in; when a
// terminal started it, borrow that terminal for output.
func attachConsole() {
	if _, err := os.Stdout.Stat(); err == nil {
		return // output is already a pipe or file
	}
	proc := syscall.NewLazyDLL("kernel32.dll").NewProc("AttachConsole")
	if r, _, _ := proc.Call(^uintptr(0)); r == 0 {
		return
	}
	if f, err := os.OpenFile("CONOUT$", os.O_WRONLY, 0); err == nil {
		os.Stdout, os.Stderr = f, f
	}
}
