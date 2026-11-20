package main

import (
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestSQLiteStorePersistsAndUpdates(t *testing.T) {
	path := filepath.Join(t.TempDir(), "auth.db")
	st, err := OpenSQLite(path)
	if err != nil {
		t.Fatal(err)
	}
	if _, found, _ := st.Hash("n1"); found {
		t.Fatal("empty store must not find n1")
	}
	h1 := sha256Hex("one")
	if err := st.Put("n1", h1); err != nil {
		t.Fatal(err)
	}
	if err := st.Put("n2", sha256Hex("two")); err != nil {
		t.Fatal(err)
	}
	h2 := sha256Hex("rotated")
	if err := st.Put("n1", h2); err != nil { // rotation replaces the record
		t.Fatal(err)
	}
	if err := st.Close(); err != nil {
		t.Fatal(err)
	}

	st, err = OpenSQLite(path) // records survive a restart
	if err != nil {
		t.Fatal(err)
	}
	defer st.Close()
	if got, found, _ := st.Hash("n1"); !found || got != h2 {
		t.Errorf("n1 after reopen: %q found=%v", got, found)
	}
	ids, _ := st.IDs()
	if strings.Join(ids, ",") != "n1,n2" {
		t.Errorf("ids: %v", ids)
	}
}

func TestSQLiteStoreNeverHoldsATokenOnDisk(t *testing.T) {
	path := filepath.Join(t.TempDir(), "auth.db")
	st, _ := OpenSQLite(path)
	_ = st.Put("n1", sha256Hex("not-stored-xyz"))
	_ = st.Close()
	raw, _ := os.ReadFile(path)
	wal, _ := os.ReadFile(path + "-wal")
	if strings.Contains(string(raw)+string(wal), "not-stored-xyz") {
		t.Fatal("the plain token must never be written to the database")
	}
}

func TestImportKVAcceptsWorkerExportAndRejectsBadRows(t *testing.T) {
	dir := t.TempDir()
	st, _ := OpenSQLite(filepath.Join(dir, "a.db"))
	defer st.Close()

	good := filepath.Join(dir, "good.json")
	_ = os.WriteFile(good, []byte(`[{"key":"relay:node-a","value":"`+sha256Hex("a")+`"},{"key":"relay:node-b","value":"`+sha256Hex("b")+`"}]`), 0o600)
	n, err := ImportKV(st, good)
	if err != nil || n != 2 {
		t.Fatalf("import: %d %v", n, err)
	}
	if h, ok, _ := st.Hash("node-a"); !ok || h != sha256Hex("a") {
		t.Errorf("node-a: %q %v", h, ok)
	}

	for name, body := range map[string]string{
		"not json":       `{`,
		"wrong key":      `[{"key":"tenant:x","value":"` + sha256Hex("x") + `"}]`,
		"bad id":         `[{"key":"relay:BAD ID","value":"` + sha256Hex("x") + `"}]`,
		"value not hash": `[{"key":"relay:ok","value":"plain-token"}]`,
		"one bad row":    `[{"key":"relay:fine","value":"` + sha256Hex("x") + `"},{"key":"relay:bad","value":"zz"}]`,
	} {
		p := filepath.Join(dir, "bad.json")
		_ = os.WriteFile(p, []byte(body), 0o600)
		if _, err := ImportKV(st, p); err == nil {
			t.Errorf("%s: import must fail", name)
		}
	}
	if _, ok, _ := st.Hash("fine"); ok {
		t.Error("a failed import must write nothing, including its valid rows")
	}
}

func TestRouteTable(t *testing.T) {
	cases := []struct {
		host, url, suffix string
		id, path          string
		ok                bool
	}{
		{"n1.relay.test", "/a?b=1", ".relay.test", "n1", "/a?b=1", true},
		{"N1.RELAY.TEST:8443", "/", ".relay.test", "n1", "/", true},
		{"relay.test", "/n/n1/x", ".relay.test", "n1", "/x", true},
		{"anything", "/n/n1", "", "n1", "/", true},
		{"anything", "/n/n1/", "", "n1", "/", true},
		{"anything", "/n/n1/a%20b?q=%2F", "", "n1", "/a%20b?q=%2F", true},
		{"evil.example", "/x", ".relay.test", "", "", false},
		{"-x.relay.test", "/x", ".relay.test", "", "", false},
		{".relay.test", "/x", ".relay.test", "", "", false},
		{"anything", "/n/Bad_Id/x", "", "", "", false},
	}
	for _, c := range cases {
		u := mustURL(t, c.url)
		id, path, ok := route(c.host, u, c.suffix)
		if id != c.id || path != c.path || ok != c.ok {
			t.Errorf("route(%q,%q,%q) = %q %q %v; want %q %q %v", c.host, c.url, c.suffix, id, path, ok, c.id, c.path, c.ok)
		}
	}
}

func mustURL(t *testing.T, s string) *url.URL {
	t.Helper()
	u, err := url.Parse(s)
	if err != nil {
		t.Fatal(err)
	}
	return u
}
