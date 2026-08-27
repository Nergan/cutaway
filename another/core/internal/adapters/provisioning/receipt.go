package provisioning

import (
	"encoding/json"
	"os"
	"path/filepath"

	"github.com/another-vpn/another/core/internal/domain"
)

const receiptName = "enrolled.json"

type Receipt struct {
	ClientID string                  `json:"client_id"`
	Nodes    []domain.NodeDescriptor `json:"nodes"`
}

func ReceiptPath(keystoreDir string) string {
	return filepath.Join(keystoreDir, receiptName)
}

func LoadReceipt(keystoreDir string) (Receipt, bool, error) {
	raw, err := os.ReadFile(ReceiptPath(keystoreDir))
	if err != nil {
		if os.IsNotExist(err) {
			return Receipt{}, false, nil
		}
		return Receipt{}, false, err
	}
	var rec Receipt
	if err := json.Unmarshal(raw, &rec); err != nil {
		return Receipt{}, false, err
	}
	if rec.ClientID == "" {
		return Receipt{}, false, nil
	}
	return rec, true, nil
}

func SaveReceipt(keystoreDir string, rec Receipt) error {
	if err := os.MkdirAll(keystoreDir, 0o700); err != nil {
		return err
	}
	raw, err := json.Marshal(rec)
	if err != nil {
		return err
	}
	return os.WriteFile(ReceiptPath(keystoreDir), raw, 0o600)
}
