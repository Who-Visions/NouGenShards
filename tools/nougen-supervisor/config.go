package main

import (
	"encoding/json"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

// Node is one account's node on this computer: a NouGenShards process on a
// local port, plus the tunnel that publishes it.
type Node struct {
	ID     string `json:"id"`
	Port   int    `json:"port"`
	Token  string `json:"token"`
	Tunnel string `json:"tunnel"`
	URL    string `json:"url,omitempty"`

	Dir    string `json:"-"` // the account's folder
	Source string `json:"-"` // which file described it: node.json, run.ps1 or run.sh
}

// SrcDir is where the account's copy of the node code lives.
func (n Node) SrcDir() string { return filepath.Join(n.Dir, "NouGenShards") }

// DefaultBase is the folder the join setup installs accounts under.
func DefaultBase() string {
	if b := os.Getenv("NOUGEN_NODE_BASE"); b != "" {
		return b
	}
	if runtime.GOOS == "windows" {
		if l := os.Getenv("LOCALAPPDATA"); l != "" {
			return filepath.Join(l, "NouGen")
		}
	}
	home, _ := os.UserHomeDir()
	return filepath.Join(home, ".nougen-node")
}

// utf8BOM is the byte-order mark PowerShell 5 puts in front of UTF-8 files.
var utf8BOM = string([]byte{0xEF, 0xBB, 0xBF})

var (
	ps1Token  = regexp.MustCompile(`\$env:NGS_NODE_TOKEN\s*=\s*'((?:[^']|'')*)'`)
	ps1Port   = regexp.MustCompile(`\$env:NGS_PORT\s*=\s*'(\d+)'`)
	ps1User   = regexp.MustCompile(`\$env:NGS_HUD_USER\s*=\s*'((?:[^']|'')*)'`)
	ps1Tunnel = regexp.MustCompile(`'--token'\s*,\s*'((?:[^']|'')*)'`)
	// In sh, a single quote inside a single-quoted value is written '\''.
	shUser   = regexp.MustCompile(`NGS_HUD_USER='((?:[^']|'\\'')*)'`)
	shToken  = regexp.MustCompile(`NGS_NODE_TOKEN='((?:[^']|'\\'')*)'`)
	shPort   = regexp.MustCompile(`NGS_PORT='(\d+)'`)
	shTunnel = regexp.MustCompile(`--token '((?:[^']|'\\'')*)'`)
)

// shValue undoes sh single-quote escaping.
func shValue(s string) string { return strings.ReplaceAll(s, `'\''`, "'") }

func first(re *regexp.Regexp, s string) string {
	m := re.FindStringSubmatch(s)
	if m == nil {
		return ""
	}
	return m[1]
}

// loadNode reads one account folder. It understands the current layout
// (node.json) and the two launcher scripts older setups wrote, so a computer
// that joined before the supervisor existed is picked up without a re-install.
func loadNode(dir string) (Node, bool) {
	n := Node{Dir: dir}
	if b, err := os.ReadFile(filepath.Join(dir, "node.json")); err == nil {
		// PowerShell 5 writes UTF-8 with a byte-order mark.
		b = []byte(strings.TrimPrefix(string(b), utf8BOM))
		if json.Unmarshal(b, &n) != nil {
			return Node{}, false
		}
		n.Dir, n.Source = dir, "node.json"
	} else if b, err := os.ReadFile(filepath.Join(dir, "run.ps1")); err == nil {
		s := string(b)
		n.Token = strings.ReplaceAll(first(ps1Token, s), "''", "'")
		n.Tunnel = strings.ReplaceAll(first(ps1Tunnel, s), "''", "'")
		n.ID = strings.ReplaceAll(first(ps1User, s), "''", "'")
		n.Port, _ = strconv.Atoi(first(ps1Port, s))
		n.Source = "run.ps1"
	} else if b, err := os.ReadFile(filepath.Join(dir, "run.sh")); err == nil {
		s := string(b)
		n.Token, n.Tunnel = shValue(first(shToken, s)), shValue(first(shTunnel, s))
		n.ID = shValue(first(shUser, s))
		n.Port, _ = strconv.Atoi(first(shPort, s))
		n.Source = "run.sh"
	} else {
		return Node{}, false
	}
	if n.ID == "" {
		n.ID = filepath.Base(dir)
	}
	if n.Port < 1 || n.Port > 65535 || n.Token == "" {
		return Node{}, false
	}
	// A folder whose download never finished has nothing to run yet.
	if _, err := os.Stat(filepath.Join(n.SrcDir(), "app.py")); err != nil {
		return Node{}, false
	}
	return n, true
}

// Discover lists every runnable account under base, ordered by port. The
// earliest setups put the first account directly in base instead of a folder
// of its own, so base itself is checked too. Two accounts claiming one port or
// one name cannot both run; the first found keeps it.
func Discover(base string) []Node {
	entries, err := os.ReadDir(base)
	if err != nil {
		return nil
	}
	dirs := []string{base}
	for _, e := range entries {
		if e.IsDir() {
			dirs = append(dirs, filepath.Join(base, e.Name()))
		}
	}
	var nodes []Node
	ports, ids := map[int]bool{}, map[string]bool{}
	for _, dir := range dirs {
		n, ok := loadNode(dir)
		if !ok {
			continue
		}
		if dir == base && n.ID == filepath.Base(base) {
			n.ID = "root"
		}
		if ports[n.Port] || ids[n.ID] {
			continue
		}
		ports[n.Port], ids[n.ID] = true, true
		nodes = append(nodes, n)
	}
	sort.Slice(nodes, func(i, j int) bool { return nodes[i].Port < nodes[j].Port })
	return nodes
}
