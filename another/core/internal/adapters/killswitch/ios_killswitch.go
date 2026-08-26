//go:build ios

package killswitch

import (
	"context"
	"errors"
)

// IOSKillSwitch — TODO v2. На iOS блокировка настраивается через
// NEPacketTunnelNetworkSettings.includeAllNetworks = true (и
// excludeLocalNetworks по необходимости) на стороне расширения
// NEPacketTunnelProvider, которое линкует это Go-ядро как библиотеку
// (см. cmd/mobilelib/binding.go). Сам Go-код не имеет прямого доступа к
// NetworkExtension API — эта настройка выставляется Swift-кодом расширения
// при вызове startTunnel(options:completionHandler:), поэтому здесь только
// координация состояния (Arm/Disarm должны быть отражены в статусе,
// который binding.go отдаёт наружу, чтобы Swift-код знал, когда обновлять
// NEPacketTunnelNetworkSettings).
type IOSKillSwitch struct{}

func NewIOSKillSwitch() *IOSKillSwitch { return &IOSKillSwitch{} }

var errNotImplementedIOS = errors.New("killswitch: NetworkExtension-based kill switch not implemented in v1 (see ios_killswitch.go)")

func (i *IOSKillSwitch) Arm(ctx context.Context) error             { return errNotImplementedIOS }
func (i *IOSKillSwitch) Disarm(ctx context.Context) error          { return errNotImplementedIOS }
func (i *IOSKillSwitch) OnTunnelDropped(ctx context.Context) error { return errNotImplementedIOS }
