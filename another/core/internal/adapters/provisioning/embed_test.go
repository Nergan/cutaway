package provisioning

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestBundleJSONHasNoPrivateKey(t *testing.T) {
	out, err := json.Marshal(Load())
	if err != nil {
		t.Fatal(err)
	}
	if strings.Contains(strings.ToLower(string(out)), "private_key") {
		t.Fatalf("must not embed private_key: %s", out)
	}
}
