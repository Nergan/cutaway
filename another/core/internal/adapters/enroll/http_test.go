package enroll

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnrollSuccess(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/enroll", func(w http.ResponseWriter, r *http.Request) {
		var body requestBody
		if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
			t.Fatalf("decode: %v", err)
		}
		if body.EnrollmentToken == "" || body.PublicKey == "" {
			t.Fatal("missing fields")
		}
		_ = json.NewEncoder(w).Encode(map[string]any{
			"ok":        true,
			"client_id": "nu-ya-test",
			"nodes": []map[string]any{{
				"name":          "cf-worker",
				"tier":          "tier1-bootstrap",
				"transport":     "vless-ws",
				"host":          "edge.example",
				"port":          443,
				"path":          "/proxy",
				"priority":      1,
				"control_plane": "https://edge.example",
			}},
		})
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	id, nodes, err := New().Enroll(context.Background(), srv.URL, "tok", "aa", "bb")
	if err != nil {
		t.Fatal(err)
	}
	if id != "nu-ya-test" {
		t.Fatalf("client_id=%q", id)
	}
	if len(nodes) != 1 || nodes[0].ControlPlane != "https://edge.example" {
		t.Fatalf("nodes=%+v", nodes)
	}
}

func TestEnrollForbiddenDoesNotLeakBody(t *testing.T) {
	mux := http.NewServeMux()
	mux.HandleFunc("/enroll", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusForbidden)
		_, _ = w.Write([]byte(`{"error":"invalid or already-used enrollment token"}`))
	})
	srv := httptest.NewServer(mux)
	defer srv.Close()

	_, _, err := New().Enroll(context.Background(), srv.URL, "used", "aa", "")
	if err == nil {
		t.Fatal("expected error")
	}
	if got := err.Error(); got != "enroll: rejected (status 403)" {
		t.Fatalf("err=%q", got)
	}
}
