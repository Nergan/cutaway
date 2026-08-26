package domain

import "testing"

func TestOrderByProbe_LiveFirstByRTT(t *testing.T) {
	nodes := []NodeDescriptor{
		{Name: "slow", Priority: 1},
		{Name: "dead", Priority: 2},
		{Name: "fast", Priority: 3},
	}
	ordered := OrderByProbe(nodes, []ProbeResult{
		{Name: "slow", OK: true, RTT: 80_000_000},
		{Name: "dead", OK: false, Err: "timeout"},
		{Name: "fast", OK: true, RTT: 10_000_000},
	})
	if ordered[0].Name != "fast" || ordered[1].Name != "slow" || ordered[2].Name != "dead" {
		t.Fatalf("order = %s,%s,%s", ordered[0].Name, ordered[1].Name, ordered[2].Name)
	}
}
