//go:build !windows

package main

import (
	"errors"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
)

// Linux autostart, in order: a systemd user service, then an @reboot crontab
// line, then nothing. Containers and sandboxes usually have neither, and that
// is not an install failure: the supervisor still runs, it just does not come
// back by itself after a restart. errNoAutostart tells the caller to say so.
var errNoAutostart = errors.New("no autostart available")

const unitName = "nougen-supervisor.service"

// hostProbe is what the choice depends on, so tests can describe any machine.
type hostProbe struct {
	Override       string // NOUGEN_AUTOSTART: auto, systemd, cron or none
	Container      bool   // /.dockerenv, /run/.containerenv, or a container cgroup
	SystemdUser    bool   // a user systemd manager answers
	CrontabPresent bool   // the crontab program exists
}

func liveProbe() hostProbe {
	p := hostProbe{Override: strings.ToLower(strings.TrimSpace(os.Getenv("NOUGEN_AUTOSTART")))}
	for _, f := range []string{"/.dockerenv", "/run/.containerenv"} {
		if _, err := os.Stat(f); err == nil {
			p.Container = true
		}
	}
	if b, err := os.ReadFile("/proc/1/cgroup"); err == nil {
		s := string(b)
		for _, k := range []string{"docker", "containerd", "kubepods", "lxc", "podman"} {
			if strings.Contains(s, k) {
				p.Container = true
			}
		}
	}
	if _, err := exec.LookPath("systemctl"); err == nil {
		p.SystemdUser = exec.Command("systemctl", "--user", "show-environment").Run() == nil
	}
	_, err := exec.LookPath("crontab")
	p.CrontabPresent = err == nil
	return p
}

// autostartPlan lists the methods to try, best first. An empty list means none.
func autostartPlan(p hostProbe) []string {
	switch p.Override {
	case "none", "foreground":
		return nil
	case "systemd", "cron":
		return []string{p.Override}
	}
	if p.Container {
		return nil
	}
	var plan []string
	if p.SystemdUser {
		plan = append(plan, "systemd")
	}
	if p.CrontabPresent {
		plan = append(plan, "cron")
	}
	return plan
}

func unitPath() string {
	dir := os.Getenv("XDG_CONFIG_HOME")
	if dir == "" {
		home, _ := os.UserHomeDir()
		dir = filepath.Join(home, ".config")
	}
	return filepath.Join(dir, "systemd", "user", unitName)
}

// sdQuote quotes one ExecStart word the way systemd reads it.
func sdQuote(s string) string {
	r := strings.NewReplacer(`\`, `\`, `"`, `\"`, "%", "%%", "$", "$$")
	return `"` + r.Replace(s) + `"`
}

func unitText(self string, args []string) string {
	words := []string{sdQuote(self)}
	for _, a := range args {
		words = append(words, sdQuote(a))
	}
	return "[Unit]\nDescription=NouGen supervisor\n\n[Service]\nExecStart=" + strings.Join(words, " ") +
		"\nRestart=on-failure\nRestartSec=10\n\n[Install]\nWantedBy=default.target\n"
}

func installSystemd(self string, args []string) error {
	if err := os.MkdirAll(filepath.Dir(unitPath()), 0o755); err != nil {
		return err
	}
	if err := os.WriteFile(unitPath(), []byte(unitText(self, args)), 0o644); err != nil {
		return err
	}
	if out, err := exec.Command("systemctl", "--user", "daemon-reload").CombinedOutput(); err != nil {
		return fmt.Errorf("systemctl daemon-reload: %v %s", err, strings.TrimSpace(string(out)))
	}
	// enable, not enable --now: install starts the supervisor itself, and two would fight over ports.
	if out, err := exec.Command("systemctl", "--user", "enable", unitName).CombinedOutput(); err != nil {
		return fmt.Errorf("systemctl enable: %v %s", err, strings.TrimSpace(string(out)))
	}
	return nil
}

func installCron(self string, args []string, base string) error {
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

func installLinux(self string, args []string, base string) error {
	var why []string
	for _, m := range autostartPlan(liveProbe()) {
		var err error
		if m == "systemd" {
			err = installSystemd(self, args)
		} else {
			err = installCron(self, args, base)
		}
		if err == nil {
			return nil
		}
		why = append(why, m+": "+err.Error())
	}
	if len(why) == 0 {
		return errNoAutostart
	}
	return fmt.Errorf("%w (%s)", errNoAutostart, strings.Join(why, "; "))
}

func linuxAutostartKind() string {
	if _, err := os.Stat(unitPath()); err == nil {
		return "systemd"
	}
	if _, err := exec.LookPath("crontab"); err == nil && strings.Contains(crontab(), cronMark) {
		return "cron"
	}
	return ""
}

func removeLinux() error {
	var errs []error
	if _, err := os.Stat(unitPath()); err == nil {
		_ = exec.Command("systemctl", "--user", "disable", unitName).Run()
		if err := os.Remove(unitPath()); err != nil {
			errs = append(errs, err)
		}
	}
	if _, err := exec.LookPath("crontab"); err == nil && strings.Contains(crontab(), cronMark) {
		errs = append(errs, writeCrontab(func(l string) bool { return !strings.Contains(l, cronMark) }, ""))
	}
	return errors.Join(errs...)
}

func isNoAutostart(err error) bool { return errors.Is(err, errNoAutostart) }
