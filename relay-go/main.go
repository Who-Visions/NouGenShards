package main

import (
	"bufio"
	"flag"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"
)

const usage = `nougen-relay-go: native relay (protocol 1), a drop-in for the Cloudflare Worker relay.

  nougen-relay-go serve  [flags]            run the relay
  nougen-relay-go auth put <id>             read the node's join token from stdin, store sha256(token)
  nougen-relay-go auth import <file.json>   load records exported from the Worker's RELAY_AUTH KV
  nougen-relay-go auth list                 list node ids (never hashes or tokens)
  nougen-relay-go version

serve flags (env var in brackets):
  -listen        address to listen on, default :8443            [RELAY_LISTEN]
  -db            auth database (SQLite file)                    [RELAY_DB]
  -host-suffix   route <id><suffix> hosts, e.g. .relay.example  [RELAY_HOST_SUFFIX]
  -tls-cert, -tls-key   serve TLS directly. Without them it speaks plain HTTP and
                 must sit behind a TLS terminator: nodes only dial wss://.
  -timeout       per-request timeout, default 30s               [RELAY_REQUEST_TIMEOUT]
  -max-body      body cap in bytes, default 8388608             [RELAY_MAX_BODY_BYTES]
`

const version = "0.1.0-spec"

func env(name, def string) string {
	if v := strings.TrimSpace(os.Getenv(name)); v != "" {
		return v
	}
	return def
}

func main() {
	if len(os.Args) < 2 {
		fmt.Fprint(os.Stderr, usage)
		os.Exit(2)
	}
	switch os.Args[1] {
	case "serve":
		os.Exit(serve(os.Args[2:]))
	case "auth":
		os.Exit(authCmd(os.Args[2:]))
	case "version":
		fmt.Println(version)
	default:
		fmt.Fprint(os.Stderr, usage)
		os.Exit(2)
	}
}

func serve(args []string) int {
	fs := flag.NewFlagSet("serve", flag.ContinueOnError)
	listen := fs.String("listen", env("RELAY_LISTEN", ":8443"), "")
	db := fs.String("db", env("RELAY_DB", "relay-auth.db"), "")
	suffix := fs.String("host-suffix", env("RELAY_HOST_SUFFIX", ""), "")
	cert := fs.String("tls-cert", "", "")
	key := fs.String("tls-key", "", "")
	timeout := fs.Duration("timeout", parseDur(env("RELAY_REQUEST_TIMEOUT", "30s")), "")
	maxBody := fs.Int64("max-body", parseInt(env("RELAY_MAX_BODY_BYTES", ""), defaultMaxBody), "")
	if err := fs.Parse(args); err != nil {
		return 2
	}
	if (*cert == "") != (*key == "") {
		log.Print("serve: -tls-cert and -tls-key go together")
		return 2
	}
	st, err := OpenSQLite(*db)
	if err != nil {
		log.Printf("serve: auth database: %v", err)
		return 1
	}
	defer st.Close()
	srv := NewServer(Config{HostSuffix: *suffix, Timeout: *timeout, MaxBody: *maxBody}, st)
	hs := &http.Server{Addr: *listen, Handler: srv, ReadHeaderTimeout: 10 * time.Second}
	if *cert != "" {
		log.Printf("relay %s listening on %s (TLS)", version, *listen)
		err = hs.ListenAndServeTLS(*cert, *key)
	} else {
		log.Printf("relay %s listening on %s (plain HTTP: put a TLS terminator in front)", version, *listen)
		err = hs.ListenAndServe()
	}
	log.Printf("serve: %v", err)
	return 1
}

func authCmd(args []string) int {
	if len(args) == 0 {
		fmt.Fprint(os.Stderr, usage)
		return 2
	}
	dbPath := env("RELAY_DB", "relay-auth.db")
	st, err := OpenSQLite(dbPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "auth: database: %v\n", err)
		return 1
	}
	defer st.Close()
	switch args[0] {
	case "put":
		if len(args) != 2 || !validID(strings.ToLower(args[1])) {
			fmt.Fprintln(os.Stderr, "auth put <id>: the token is read from stdin, never from arguments")
			return 2
		}
		tok, _ := bufio.NewReader(io.LimitReader(os.Stdin, 4096)).ReadString('\n')
		tok = strings.TrimSpace(tok)
		if tok == "" {
			fmt.Fprintln(os.Stderr, "auth put: no token on stdin")
			return 2
		}
		if err := st.Put(strings.ToLower(args[1]), sha256Hex(tok)); err != nil {
			fmt.Fprintf(os.Stderr, "auth put: %v\n", err)
			return 1
		}
		fmt.Println("stored:", strings.ToLower(args[1]))
	case "import":
		if len(args) != 2 {
			fmt.Fprintln(os.Stderr, "auth import <file.json>")
			return 2
		}
		n, err := ImportKV(st, args[1])
		if err != nil {
			fmt.Fprintf(os.Stderr, "auth import: %v\n", err)
			return 1
		}
		fmt.Printf("imported %d records\n", n)
	case "list":
		ids, err := st.IDs()
		if err != nil {
			fmt.Fprintf(os.Stderr, "auth list: %v\n", err)
			return 1
		}
		for _, id := range ids {
			fmt.Println(id)
		}
	default:
		fmt.Fprint(os.Stderr, usage)
		return 2
	}
	return 0
}

func parseDur(s string) time.Duration {
	d, err := time.ParseDuration(s)
	if err != nil {
		return defaultTimeout
	}
	return d
}

func parseInt(s string, def int64) int64 {
	var n int64
	if _, err := fmt.Sscanf(s, "%d", &n); err != nil || n <= 0 {
		return def
	}
	return n
}
