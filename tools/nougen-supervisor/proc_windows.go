//go:build windows

package main

import (
	"fmt"
	"os"
	"os/exec"
	"strconv"
	"strings"
	"syscall"
)

const (
	createNoWindow        = 0x08000000
	createNewProcessGroup = 0x00000200
	processTerminate      = 0x0001
	processSetQuota       = 0x0100
	runKey                = `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`
	runName               = "NouGen-Supervisor"
)

var (
	kernel32            = syscall.NewLazyDLL("kernel32.dll")
	procCreateJobObject = kernel32.NewProc("CreateJobObjectW")
	procAssignToJob     = kernel32.NewProc("AssignProcessToJobObject")
	procTerminateJob    = kernel32.NewProc("TerminateJobObject")
	procAttachConsole   = kernel32.NewProc("AttachConsole")
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

// track puts a freshly started child in a job object of its own. Everything
// the child starts later (uv starts Python) lands in the same job, so the
// tree can be stopped through the job handle instead of by process id.
// The job is not set to die with this program: nodes outlive the supervisor.
func track(cmd *exec.Cmd) uintptr {
	job, _, _ := procCreateJobObject.Call(0, 0)
	if job == 0 {
		return 0
	}
	h, err := syscall.OpenProcess(processTerminate|processSetQuota, false, uint32(cmd.Process.Pid))
	if err != nil {
		syscall.CloseHandle(syscall.Handle(job))
		return 0
	}
	ok, _, _ := procAssignToJob.Call(job, uintptr(h))
	syscall.CloseHandle(h)
	if ok == 0 {
		syscall.CloseHandle(syscall.Handle(job))
		return 0
	}
	return job
}

// killGroup stops a child and everything it started. With a job it never
// names a process id. Without one (grouping failed) it falls back to
// taskkill, and only while the child is still running, so the id it names
// cannot have been handed to another program.
func killGroup(p *proc) {
	if p == nil || p.cmd == nil || p.cmd.Process == nil {
		return
	}
	if p.group != 0 {
		procTerminateJob.Call(p.group, 1)
		return
	}
	if p.alive() {
		if hidden("taskkill", "/T", "/F", "/PID", strconv.Itoa(p.cmd.Process.Pid)).Run() != nil {
			_ = p.cmd.Process.Kill()
		}
	}
}

func closeGroup(p *proc) {
	if p != nil && p.group != 0 {
		syscall.CloseHandle(syscall.Handle(p.group))
		p.group = 0
	}
}

// portOwner finds the program listening on a local port and its command line.
func portOwner(port int) (int, string) {
	out, err := hidden("netstat", "-ano", "-p", "TCP").Output()
	if err != nil {
		return 0, ""
	}
	suffix := ":" + strconv.Itoa(port)
	pid := 0
	for _, line := range strings.Split(string(out), "\n") {
		f := strings.Fields(line)
		if len(f) >= 5 && f[3] == "LISTENING" && strings.HasSuffix(f[1], suffix) {
			pid, _ = strconv.Atoi(f[4])
			break
		}
	}
	if pid <= 4 {
		return 0, ""
	}
	q := fmt.Sprintf("(Get-CimInstance Win32_Process -Filter 'ProcessId=%d').CommandLine", pid)
	cl, _ := hidden("powershell", "-NoProfile", "-NonInteractive", "-Command", q).Output()
	return pid, strings.TrimSpace(string(cl))
}

// killPID stops a program this supervisor did not start, with its children.
// Callers confirm what the id belongs to immediately before calling.
func killPID(pid int) {
	_ = hidden("taskkill", "/T", "/F", "/PID", strconv.Itoa(pid)).Run()
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
	// Older setups registered one launcher per account (and "NouGen" for the
	// first one). Left in place they would race this program at sign-in for
	// the same ports. Only values that point at a run.ps1 launcher are removed.
	for _, id := range ids {
		name := "NouGen-" + id
		if id == "root" {
			name = "NouGen"
		}
		out, err := hidden("reg", "query", runKey, "/v", name).Output()
		if err == nil && strings.Contains(string(out), "run.ps1") {
			_ = hidden("reg", "delete", runKey, "/v", name, "/f").Run()
		}
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

// stopOthers ends every other supervisor process. A build from before the
// control endpoint existed cannot be asked to quit, and two supervisors would
// fight over the same ports.
func stopOthers() {
	_ = hidden("taskkill", "/F", "/IM", "nougen-supervisor.exe", "/FI", "PID ne "+strconv.Itoa(os.Getpid())).Run()
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
	if r, _, _ := procAttachConsole.Call(^uintptr(0)); r == 0 {
		return
	}
	if f, err := os.OpenFile("CONOUT$", os.O_WRONLY, 0); err == nil {
		os.Stdout, os.Stderr = f, f
	}
}
