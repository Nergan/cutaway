//go:build ios

package tun

import (
	"context"
	"errors"

	"github.com/another-vpn/another/core/internal/ports"
)

// IOSTun — TODO v2. На iOS TUN — это packetFlow объекта
// NEPacketTunnelProvider (Swift-сторона расширения). Данные передаются через
// NEPacketTunnelFlow.readPackets(completionHandler:)/writePackets(_:withProtocols:),
// у которых нет прямого Go-аналога — обычно этот мост реализуется как пара
// каналов между Swift и Go-библиотекой (gomobile bind), либо через
// файловый дескриптор сокета, если расширение явно его создаёт. Строгий
// лимит памяти extension-процесса (см. §5.2 спецификации, актуально
// ~50 МБ для packet-tunnel, не задокументировано официально Apple) — ещё
// одна причина, почему этот адаптер должен быть максимально экономным по
// аллокациям в v2.
type IOSTun struct{}

func NewIOSTun() *IOSTun { return &IOSTun{} }

var errNotImplementedIOSTun = errors.New("tun: NEPacketTunnelProvider-based TUN not implemented in v1 (see ios_tun.go)")

func (i *IOSTun) Bind(ctx context.Context, tunnel ports.Tunnel) error { return errNotImplementedIOSTun }
func (i *IOSTun) Unbind(ctx context.Context) error                    { return errNotImplementedIOSTun }
