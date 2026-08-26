package domain

import "sort"

// FailoverPolicy определяет порядок перебора узлов при подключении
// (см. псевдокод §5.3 спецификации: Cloudflare Worker → Render → VPS Reality
// либо иной порядок, заданный профилем пользователя).
type FailoverPolicy struct {
	Candidates []NodeDescriptor
}

// NewFailoverPolicy сортирует кандидатов по Priority (по возрастанию —
// меньшее число означает более высокий приоритет) один раз при создании,
// чтобы use-case не занимался сортировкой на каждый Connect().
func NewFailoverPolicy(candidates []NodeDescriptor) *FailoverPolicy {
	sorted := make([]NodeDescriptor, len(candidates))
	copy(sorted, candidates)
	sort.SliceStable(sorted, func(i, j int) bool {
		return sorted[i].Priority < sorted[j].Priority
	})
	return &FailoverPolicy{Candidates: sorted}
}

// Ordered возвращает узлы в порядке, в котором их следует пробовать.
func (p *FailoverPolicy) Ordered() []NodeDescriptor {
	return p.Candidates
}
