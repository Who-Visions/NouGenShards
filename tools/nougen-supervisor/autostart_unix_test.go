//go:build !windows

package main

import (
	"errors"
	"os"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
)

func TestAutostartPlanFallsBackInOrder(t *testing.T) {
	cases := []struct {
		name string
		p    hostProbe
		want []string
	}{
		{"desktop with systemd and cron", hostProbe{SystemdUser: true, CrontabPresent: true}, []string{"systemd", "cron"}},
		{"server without systemd user manager", hostProbe{CrontabPresent: true}, []string{"cron"}},
		{"sandbox: no systemd, no cron", hostProbe{}, nil},
		{"container even with cron installed", hostProbe{Container: true, CrontabPresent: true}, nil},
		{"override none", hostProbe{Override: "none", SystemdUser: true}, nil},
		{"override cron", hostProbe{Override: "cron", SystemdUser: true}, []string{"cron"}},
	}
	for _, c := range cases {
		if got := autostartPlan(c.p); !reflect.DeepEqual(got, c.want) {
			t.Errorf("%s: got %v want %v", c.name, got, c.want)
		}
	}
}

func TestNoAutostartIsAWarningNotAFailure(t *testing.T) {
	t.Setenv("NOUGEN_AUTOSTART", "none")
	err := installLinux("/x/nougen-supervisor", []string{"run"}, t.TempDir())
	if !isNoAutostart(err) {
		t.Fatalf("want errNoAutostart, got %v", err)
	}
	if isNoAutostart(errors.New("crontab exec error")) {
		t.Fatal("an unrelated error must not read as no-autostart")
	}
}

func TestUnitTextQuotesForSystemd(t *testing.T) {
	u := unitText("/opt/o'k/$b/nougen-supervisor", []string{"run", "-base", "/a b/100%"})
	for _, want := range []string{`ExecStart="/opt/o'k/$$b/nougen-supervisor" "run" "-base" "/a b/100%%"`, "WantedBy=default.target"} {
		if !strings.Contains(u, want) {
			t.Fatalf("unit missing %q:\n%s", want, u)
		}
	}
}

func TestForegroundCmdIsPasteable(t *testing.T) {
	if got := foregroundCmd("/home/a/.nougen-node/nougen-supervisor", []string{"run"}); got != "/home/a/.nougen-node/nougen-supervisor run" {
		t.Fatal(got)
	}
	if got := foregroundCmd("/o'k dir/s", nil); got != `'/o'\''k dir/s'` {
		t.Fatal(got)
	}
}

func TestTunnelEnvAllowlist(t *testing.T) {
	d := t.TempDir()
	body := "TUNNEL_TRANSPORT_PROTOCOL=http2\nTUNNEL_EDGE=198.41.192.7:7844,198.41.200.7:7844\nTUNNEL_TOKEN=steal\nPATH=/evil\nTUNNEL_REGION=bad value\n"
	if err := os.WriteFile(filepath.Join(d, "tunnel.env"), []byte(body), 0o600); err != nil {
		t.Fatal(err)
	}
	got := tunnelEnv(d)
	want := []string{"TUNNEL_TRANSPORT_PROTOCOL=http2", "TUNNEL_EDGE=198.41.192.7:7844,198.41.200.7:7844"}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("got %v want %v", got, want)
	}
	if tunnelEnv(t.TempDir()) != nil {
		t.Fatal("no file means no extra settings")
	}
}
