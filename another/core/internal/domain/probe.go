package domain

import "sort"

// ProbeResult — результат пробника входа (TCP/TLS RTT), не DPI-тест.
type ProbeResult struct {
	Name string
	OK   bool
	RTT  int64 // наносекунды; 0 если !OK
	Err  string
}

// OrderByProbe ставит живые узлы впереди по RTT, мёртвые — в хвост.
// При равном RTT сохраняется исходный Priority-порядок (stable).
func OrderByProbe(nodes []NodeDescriptor, results []ProbeResult) []NodeDescriptor {
	byName := make(map[string]ProbeResult, len(results))
	for _, r := range results {
		byName[r.Name] = r
	}
	out := make([]NodeDescriptor, len(nodes))
	copy(out, nodes)
	sort.SliceStable(out, func(i, j int) bool {
		ri, iok := byName[out[i].Name]
		rj, jok := byName[out[j].Name]
		if iok && ri.OK && (!jok || !rj.OK) {
			return true
		}
		if jok && rj.OK && (!iok || !ri.OK) {
			return false
		}
		if iok && jok && ri.OK && rj.OK {
			return ri.RTT < rj.RTT
		}
		return false
	})
	return out
}
