//go:build linux && !android

package killswitch

import (
	"strings"
	"testing"
)

func TestRenderNFTIncludesPermitAndIface(t *testing.T) {
	ks := &LinuxKillSwitch{Interface: "another0", permit: []string{"1.2.3.4"}}
	s := ks.renderNFT(false)
	for _, want := range []string{"another0", "1.2.3.4", "policy drop", "oif lo accept"} {
		if !strings.Contains(s, want) {
			t.Fatalf("script missing %q:\n%s", want, s)
		}
	}
}
