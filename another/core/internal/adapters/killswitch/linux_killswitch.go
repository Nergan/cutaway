//go:build linux && !android

package killswitch

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"strings"
	"sync"
)

const nftTable = "another"

// LinuxKillSwitch — таблица inet another в nftables. Permit — IP входов
// и control-plane, чтобы reconnect не резался.
type LinuxKillSwitch struct {
	Interface string
	mu        sync.Mutex
	permit    []string
	armed     bool
}

func NewLinuxKillSwitch() *LinuxKillSwitch {
	ifn := os.Getenv("ANOTHER_TUN_IF")
	if ifn == "" {
		ifn = "another0"
	}
	return &LinuxKillSwitch{Interface: ifn}
}

func (l *LinuxKillSwitch) SetPermitDestinations(addrs []string) {
	l.mu.Lock()
	l.permit = append([]string(nil), addrs...)
	l.mu.Unlock()
}

func (l *LinuxKillSwitch) Arm(ctx context.Context) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	script := l.renderNFT(false)
	if err := nftApply(ctx, script); err != nil {
		return err
	}
	l.armed = true
	return nil
}

func (l *LinuxKillSwitch) Disarm(ctx context.Context) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	_ = exec.CommandContext(ctx, "nft", "delete", "table", "inet", nftTable).Run()
	l.armed = false
	return nil
}

func (l *LinuxKillSwitch) OnTunnelDropped(ctx context.Context) error {
	l.mu.Lock()
	defer l.mu.Unlock()
	return nftApply(ctx, l.renderNFT(true))
}

func (l *LinuxKillSwitch) renderNFT(dropAllNonPermit bool) string {
	var b strings.Builder
	b.WriteString("flush table inet " + nftTable + "\n")
	b.WriteString("table inet " + nftTable + " {\n")
	b.WriteString("  chain output {\n")
	b.WriteString("    type filter hook output priority 0; policy drop;\n")
	b.WriteString("    oifname \"" + l.Interface + "\" accept\n")
	b.WriteString("    oif lo accept\n")
	for _, p := range l.permit {
		if p != "" {
			fmt.Fprintf(&b, "    ip daddr %s accept\n", p)
			fmt.Fprintf(&b, "    ip6 daddr %s accept\n", p)
		}
	}
	if !dropAllNonPermit {
		b.WriteString("    ct state established,related accept\n")
	}
	b.WriteString("  }\n}\n")
	return b.String()
}

func nftApply(ctx context.Context, script string) error {
	_ = exec.CommandContext(ctx, "nft", "add", "table", "inet", nftTable).Run()
	cmd := exec.CommandContext(ctx, "nft", "-f", "-")
	cmd.Stdin = strings.NewReader(script)
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("killswitch: nft: %w (%s)", err, out)
	}
	return nil
}
