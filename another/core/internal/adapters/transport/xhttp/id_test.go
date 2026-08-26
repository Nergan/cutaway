package xhttp

import (
	"strings"
	"testing"
)

func TestNewSessionIDNotUUIDShape(t *testing.T) {
	sid := NewSessionID()
	if len(sid) != 32 {
		t.Fatalf("len=%d", len(sid))
	}
	if strings.Contains(sid, "-") {
		t.Fatal("session id must not look like UUID")
	}
}

func TestJoinURL(t *testing.T) {
	u := JoinURL("https://example.com:443/", "/xhttp", "abcd")
	if u != "https://example.com:443/xhttp/abcd" {
		t.Fatal(u)
	}
}
