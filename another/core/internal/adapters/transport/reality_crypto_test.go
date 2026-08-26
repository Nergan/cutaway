package transport

import "testing"

func TestParseRealityPubAndShortID(t *testing.T) {
	pub := stringsRepeat("ab", 32)
	b, err := parseRealityPub(pub)
	if err != nil || len(b) != 32 {
		t.Fatalf("%v %d", err, len(b))
	}
	if _, err := parseRealityPub("zz"); err == nil {
		t.Fatal("expected error")
	}
	sid, err := parseShortID("aabb")
	if err != nil || sid[0] != 0xaa || sid[1] != 0xbb {
		t.Fatalf("%v %x", err, sid)
	}
}

func stringsRepeat(s string, n int) string {
	out := make([]byte, 0, len(s)*n)
	for i := 0; i < n; i++ {
		out = append(out, s...)
	}
	return string(out)
}
