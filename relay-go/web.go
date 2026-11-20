package main

import (
	"bytes"
	"crypto/sha256"
	_ "embed"
	"encoding/base64"
	"net/http"
	"strconv"
)

// The public front page. Static: it names no node, count, liveness or version, so serving it
// leaks nothing that /_relay/status deliberately withholds without the node's token.
//
//go:embed web/index.html
var indexHTML []byte

// frontPageCSP pins the page's single inline <style> block by hash and allows nothing else: no
// script, no webfonts, no remote images, no framing, no forms. If the style block cannot be found
// the policy simply omits style-src, so the browser blocks the inline CSS (an unstyled page)
// instead of being given a looser policy.
var frontPageCSP = buildFrontPageCSP(indexHTML)

func buildFrontPageCSP(page []byte) string {
	csp := "default-src 'self'; script-src 'none'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; object-src 'none'"
	open, close := []byte("<style>"), []byte("</style>")
	i := bytes.Index(page, open)
	if i < 0 {
		return csp
	}
	rest := page[i+len(open):]
	j := bytes.Index(rest, close)
	if j < 0 {
		return csp
	}
	sum := sha256.Sum256(rest[:j])
	return csp + "; style-src 'sha256-" + base64.StdEncoding.EncodeToString(sum[:]) + "'"
}

// serveFrontPage answers exactly GET / and HEAD / when the request is not for a node. Callers
// have already ruled out node routes (<id>.<suffix> and /n/<id>/...), so "/" never becomes one.
func serveFrontPage(w http.ResponseWriter, r *http.Request) {
	h := w.Header()
	h.Set("content-type", "text/html; charset=utf-8")
	h.Set("content-security-policy", frontPageCSP)
	h.Set("x-content-type-options", "nosniff")
	h.Set("x-frame-options", "DENY")
	h.Set("referrer-policy", "no-referrer")
	h.Set("cache-control", "public, max-age=300")
	h.Set("content-length", strconv.Itoa(len(indexHTML)))
	w.WriteHeader(http.StatusOK)
	if r.Method != http.MethodHead {
		_, _ = w.Write(indexHTML)
	}
}
