// Package mobilelib — composition root для Android/iOS (см. §5.2
// спецификации). В отличие от cmd/desktop, здесь нет отдельного процесса и
// HTTP-сервера: экспортируемые функции этого пакета предназначены для сборки
// инструментом `gomobile bind` в .aar (Android) / .xcframework (iOS) и
// вызова напрямую из Kotlin/Swift через сгенерированные биндинги, которые
// затем Flutter дёргает через dart:ffi/platform channel (см. §6.2
// спецификации, core_bridge/ffi_core_adapter.dart).
//
// ВАЖНО: gomobile bind не может быть выполнен в этой песочнице (нет
// Android SDK/Xcode и нет доступа к module proxy для
// golang.org/x/mobile — тот же класс ограничений, что и в go.mod). Этот
// файл — валидный Go-код, собирающийся как часть модуля обычным `go build`,
// но чтобы получить из него реальный .aar/.xcframework, потребуется:
//
//	go install golang.org/x/mobile/cmd/gomobile@latest
//	gomobile bind -target=android ./cmd/mobilelib
//	iOS вне релиза (ADR 0007). Скрипт: core/scripts/gomobile-android.sh
//
// Ограничение gomobile bind: экспортируемые функции могут принимать/
// возвращать только простые типы (string, []byte, int, bool, error) — без
// произвольных структур с методами. Поэтому здесь всё завёрнуто в
// JSON-строки на границе, а не передаются структуры domain/ports напрямую.
package mobilelib

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"os"
	"sync"

	"github.com/another-vpn/another/core/internal/adapters/auth"
	"github.com/another-vpn/another/core/internal/adapters/keystore"
	"github.com/another-vpn/another/core/internal/adapters/killswitch"
	"github.com/another-vpn/another/core/internal/adapters/transport"
	"github.com/another-vpn/another/core/internal/adapters/tun"
	"github.com/another-vpn/another/core/internal/app"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

var (
	initOnce     sync.Once
	session      *domain.TunnelSession
	connectUC    *app.ConnectUseCase
	disconnUC    *app.DisconnectUseCase
	switchUC     *app.SwitchNodeUseCase
	policyOnce   *domain.FailoverPolicy
	pendingTunFd int
	ksPort       ports.KillSwitchPort
	logger       = slog.New(slog.NewTextHandler(os.Stdout, nil))
)

// GetPublicKey возвращает (создавая при первом вызове) публичный ключ
// устройства в hex — то же самое, что делает GET /identity в cmd/desktop,
// но как отдельная функция, вызываемая ДО Init(), т.к. на момент получения
// публичного ключа для отправки в edge/enroll серверный client_id ещё не
// известен (см. §7.1 спецификации и комментарий в domain.DeviceIdentity).
// keyStoreDir — та же директория, что будет передана в Init() позже; важно
// использовать один и тот же путь оба раза, иначе ключ, отправленный на
// сервер, и ключ, используемый при первом /auth, разойдутся.
func GetPublicKey(keyStoreDir string) string {
	ks := keystore.NewFileKeyStore(keyStoreDir)
	identity, err := ks.LoadOrCreateDeviceIdentity()
	if err != nil {
		return errorJSON(err)
	}
	out, _ := json.Marshal(map[string]any{
		"ok":                 true,
		"public_key":         identity.PublicKeyHex(),
		"public_key_mldsa65": identity.MLDSAPublicKeyHex(),
	})
	return string(out)
}

// SetTunFd принимает fd от VpnService.Builder.establish(). Вызывать ДО Init
// или сразу после — тогда Tunnel в use-case'ах заменяется на Android TUN.
func SetTunFd(fd int) string {
	pendingTunFd = fd
	if fd <= 0 {
		return errorJSON(fmt.Errorf("mobilelib: invalid tun fd %d", fd))
	}
	if connectUC != nil {
		stacked, err := tun.NewAndroidTunFromFD(fd, logger)
		if err != nil {
			return errorJSON(err)
		}
		connectUC.Tunnel = stacked
		if disconnUC != nil {
			disconnUC.Tunnel = stacked
		}
		if switchUC != nil {
			switchUC.Tunnel = stacked
		}
	}
	return `{"ok":true}`
}

// NotifyKillSwitchArmed — Kotlin подтверждает, что VpnService blocking TUN
// уже поднят (allowBypass=false). Без этого Arm() на Android — предупреждение.
func NotifyKillSwitchArmed() string {
	if confirmer, ok := ksPort.(interface{ ConfirmNative() }); ok {
		confirmer.ConfirmNative()
	}
	return `{"ok":true}`
}

// Init должен быть вызван один раз со стороны Kotlin/Swift перед Connect,
// с clientID и путём к директории, куда можно писать (на Android/iOS это
// обычно App's private container directory — Context.getFilesDir() /
// FileManager default directory, передаётся снаружи, т.к. Go-код на мобильных
// платформах не имеет собственного понятия "домашней директории").
//
// nodesJSON — сериализованный список domain.NodeDescriptor, полученный
// Flutter-слоем от control-plane при онбординге (§7.1 спецификации) и
// проброшенный через platform channel в этот вызов.
func Init(clientID, keyStoreDir, nodesJSON string) string {
	var initErr error
	initOnce.Do(func() {
		var nodes []domain.NodeDescriptor
		if err := json.Unmarshal([]byte(nodesJSON), &nodes); err != nil {
			initErr = err
			return
		}

		session = domain.NewTunnelSession()
		ks := keystore.NewFileKeyStore(keyStoreDir)
		authAdapter := auth.NewHTTPChallengeAdapter()
		wsTransport := transport.NewMuxTransport()

		tunAdapter := tun.SelectTun(logger)
		if pendingTunFd > 0 {
			if stacked, err := tun.NewAndroidTunFromFD(pendingTunFd, logger); err == nil {
				tunAdapter = stacked
			}
		}
		killSwitch := killswitch.SelectKillSwitch(logger)
		ksPort = killSwitch

		connectUC = app.NewConnectUseCase(session, ks, authAdapter, wsTransport, tunAdapter, killSwitch, nil, clientID, logger)
		connectUC.Prober = nil
		disconnUC = app.NewDisconnectUseCase(session, tunAdapter, killSwitch, logger)
		switchUC = app.NewSwitchNodeUseCase(session, ks, authAdapter, wsTransport, tunAdapter, clientID, logger)
		policyOnce = domain.NewFailoverPolicy(nodes)
	})
	if initErr != nil {
		return errorJSON(initErr)
	}
	return `{"ok":true}`
}

// Connect запускает подключение с failover по узлам, переданным в Init.
// destHost/destPort — см. комментарий к app.ConnectUseCase.Execute в v1
// (полноценный перехват произвольных адресов из TUN — задача v2).
func Connect(destHost string, destPort int) string {
	if connectUC == nil {
		return errorJSON(errNotInitialized)
	}
	if err := connectUC.Execute(context.Background(), policyOnce, destHost, uint16(destPort)); err != nil {
		return errorJSON(err)
	}
	return `{"ok":true}`
}

// Disconnect завершает активное соединение.
func Disconnect() string {
	if disconnUC == nil {
		return errorJSON(errNotInitialized)
	}
	if err := disconnUC.Execute(context.Background()); err != nil {
		return errorJSON(err)
	}
	return `{"ok":true}`
}

// SwitchNode переключает активное соединение на конкретный узел, выбранный
// пользователем вручную (см. app.SwitchNodeUseCase — в отличие от повторного
// Connect, держит kill switch armed на протяжении всего переключения).
// nodeJSON — сериализованный domain.NodeDescriptor.
func SwitchNode(nodeJSON, destHost string, destPort int) string {
	if switchUC == nil {
		return errorJSON(errNotInitialized)
	}
	var node domain.NodeDescriptor
	if err := json.Unmarshal([]byte(nodeJSON), &node); err != nil {
		return errorJSON(err)
	}
	if err := switchUC.Execute(context.Background(), node, destHost, uint16(destPort)); err != nil {
		return errorJSON(err)
	}
	return `{"ok":true}`
}

// Status возвращает текущее состояние сессии как JSON — этот же формат
// используется в §6.2 спецификации для ConfigRepositoryPort/UI на стороне
// Flutter.
func Status() string {
	if session == nil {
		return `{"state":"disconnected"}`
	}
	snap := session.Snapshot()
	resp := map[string]any{
		"state":      snap.State.String(),
		"bytes_sent": snap.BytesSent,
		"bytes_recv": snap.BytesRecv,
	}
	if snap.ActiveNode != nil {
		resp["active_node"] = snap.ActiveNode.Name
	}
	out, _ := json.Marshal(resp)
	return string(out)
}

var errNotInitialized = &notInitializedError{}

type notInitializedError struct{}

func (e *notInitializedError) Error() string { return "mobilelib: Init() was not called" }

func errorJSON(err error) string {
	out, _ := json.Marshal(map[string]any{"ok": false, "error": err.Error()})
	return string(out)
}
