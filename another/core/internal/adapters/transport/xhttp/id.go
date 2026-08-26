package xhttp

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"net/http"
	"strings"
)

const DefaultPath = "/xhttp"

// NewSessionID — 16 случайных байт в hex (не UUID: часть WAF режет канонический UUID).
func NewSessionID() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	return hex.EncodeToString(b[:])
}

func JoinURL(base, path, sid string) string {
	base = strings.TrimRight(base, "/")
	path = "/" + strings.Trim(path, "/")
	if path == "/" {
		path = DefaultPath
	}
	return fmt.Sprintf("%s%s/%s", base, path, sid)
}

func CopyBrowserHeaders(h http.Header) {
	h.Set("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
	h.Set("Accept", "*/*")
	h.Set("Accept-Language", "en-US,en;q=0.9")
}
