package provisioning

import (
	"encoding/json"
	"os"
	"strings"

	"github.com/another-vpn/another/core/internal/domain"
)

// Значения задаются -ldflags при per-client сборке из админки (фаза 3 кнопка).
// Не приватный ключ — только token, client_id, входы. См. docs/provisioning.md.
var (
	embeddedToken     = ""
	embeddedClientID  = ""
	embeddedBuildID   = ""
	embeddedNodesJSON = ""
)

type Bundle struct {
	EnrollmentToken string                  `json:"enrollment_token"`
	ClientID        string                  `json:"client_id"`
	BuildID         string                  `json:"build_id"`
	Entrypoints     []domain.NodeDescriptor `json:"entrypoints"`
}

func Load() Bundle {
	b := Bundle{
		EnrollmentToken: first(os.Getenv("ANOTHER_ENROLLMENT_TOKEN"), embeddedToken),
		ClientID:        first(os.Getenv("ANOTHER_CLIENT_ID"), embeddedClientID),
		BuildID:         first(os.Getenv("ANOTHER_BUILD_ID"), embeddedBuildID),
	}
	raw := first(os.Getenv("ANOTHER_NODES_JSON"), embeddedNodesJSON)
	if raw != "" {
		_ = json.Unmarshal([]byte(raw), &b.Entrypoints)
	}
	return b
}

func (b Bundle) ForgetToken() Bundle {
	b.EnrollmentToken = ""
	return b
}

func first(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}
