// NouGen Relay, native Go edition. Protocol 1: the same wire format the Cloudflare
// Worker speaks (workers/relay/worker.js), so the Python node client
// (src/nougen_shards/relay_client.py) connects to either one unchanged.
package main

import (
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/url"
	"regexp"
	"strings"
	"time"
)

// Protocol is the frame protocol version sent in the "ready" frame.
const Protocol = 1

const (
	defaultTimeout = 30 * time.Second
	defaultMaxBody = 8 << 20 // 8 MiB, same default as RELAY_MAX_BODY_BYTES

	// CloseReplaced is the WebSocket close code sent to a node whose session was
	// replaced by a newer connect for the same id.
	CloseReplaced = 4000
)

var idRE = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{0,62}$`)

func validID(id string) bool { return idRE.MatchString(id) }

// hop lists headers that never cross the relay in either direction.
var hop = map[string]bool{
	"connection": true, "keep-alive": true, "proxy-connection": true,
	"transfer-encoding": true, "upgrade": true, "te": true, "trailer": true,
	"host": true, "content-length": true,
}

// readyFrame is the first frame the relay sends after a node connects.
type readyFrame struct {
	T     string `json:"t"`
	V     int    `json:"v"`
	Since int64  `json:"since"`
}

// reqFrame carries one public HTTP request down to the node.
type reqFrame struct {
	T       string            `json:"t"`
	Rid     string            `json:"rid"`
	Method  string            `json:"method"`
	Path    string            `json:"path"`
	Headers map[string]string `json:"headers"`
	Body    string            `json:"body"` // base64 (standard alphabet)
}

// rawNumber and rawJSONOrNull keep a field exactly as the node sent it until it is checked.
type (
	rawNumber     = json.RawMessage
	rawJSONOrNull = json.RawMessage
)

// resFrame is the node's answer. The node is outside the trust boundary, so
// Status, Headers and Body stay raw until they are validated.
type resFrame struct {
	T       string        `json:"t"`
	Rid     string        `json:"rid"`
	Status  rawNumber     `json:"status"`
	Headers rawJSONOrNull `json:"headers"`
	Body    rawJSONOrNull `json:"body"`
}

// sha256Hex is what the relay stores for a node: the hash of its join token.
func sha256Hex(s string) string {
	sum := sha256.Sum256([]byte(s))
	return hex.EncodeToString(sum[:])
}

func hashesEqual(a, b string) bool {
	if len(a) != len(b) {
		return false
	}
	return subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

var bearerRE = regexp.MustCompile(`(?i)^Bearer\s+(\S+)$`)

// bearer returns the token from an Authorization header, or "".
func bearer(h http.Header) string {
	m := bearerRE.FindStringSubmatch(h.Get("Authorization"))
	if m == nil {
		return ""
	}
	return m[1]
}

var nPathRE = regexp.MustCompile(`^/n/([^/]+)(/.*)?$`)

// route says which node a public request belongs to and the path it should see.
// Two shapes, same as the Worker: <id><hostSuffix> (hostSuffix includes its leading
// dot, e.g. ".relay.example") and /n/<id>/<path> on any host.
func route(host string, u *url.URL, hostSuffix string) (id, path string, ok bool) {
	host = strings.ToLower(host)
	if i := strings.LastIndex(host, ":"); i >= 0 && !strings.Contains(host[i:], "]") {
		host = host[:i]
	}
	suffix := strings.ToLower(hostSuffix)
	if suffix != "" && strings.HasSuffix(host, suffix) {
		id = strings.TrimSuffix(host, suffix)
		if validID(id) {
			return id, withQuery(u.EscapedPath(), u.RawQuery), true
		}
	}
	if m := nPathRE.FindStringSubmatch(u.EscapedPath()); m != nil && validID(m[1]) {
		p := m[2]
		if p == "" {
			p = "/"
		}
		return m[1], withQuery(p, u.RawQuery), true
	}
	return "", "", false
}

func withQuery(p, q string) string {
	if q == "" {
		return p
	}
	return p + "?" + q
}
