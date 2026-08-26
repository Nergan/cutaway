package transport

import (
	"context"
	"io"

	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

// EchoTransport — рабочая (не заглушка) dev/test-реализация
// OutboundTransportPort, ничего не отправляющая по сети: всё, что в неё
// пишут, тут же можно прочитать обратно. Не имеет отношения к обходу DPI —
// используется только для:
//   - unit-тестов app.ConnectUseCase (проверка failover-логики без реальной
//     сети, см. internal/app/usecases_test.go);
//   - ручного end-to-end смоук-теста связки GUI↔Core↔killswitch на машине
//     разработчика до того, как поднят реальный Cloudflare Worker.
type EchoTransport struct {
	// FailFor — если не nil, Dial вернёт эту ошибку для любого узла с именем
	// из этого набора; используется в тестах для симуляции "узел недоступен".
	FailFor map[string]error
}

func NewEchoTransport() *EchoTransport {
	return &EchoTransport{FailFor: map[string]error{}}
}

func (t *EchoTransport) Dial(ctx context.Context, node domain.NodeDescriptor, creds *domain.SessionCredentials, destHost string, destPort uint16) (ports.Tunnel, error) {
	if err, ok := t.FailFor[node.Name]; ok {
		return nil, err
	}
	r1, w1 := io.Pipe()
	return &echoTunnel{r: r1, w: w1}, nil
}

type echoTunnel struct {
	r *io.PipeReader
	w *io.PipeWriter
}

func (e *echoTunnel) Read(p []byte) (int, error) {
	return e.r.Read(p)
}

func (e *echoTunnel) Write(p []byte) (int, error) {
	// Пишем в отдельной горутине, чтобы Write не блокировался в ожидании
	// Read с той же стороны (io.Pipe синхронен) — эмулируем полнодуплексное
	// эхо-соединение.
	go func(data []byte) {
		_, _ = e.w.Write(data)
	}(append([]byte(nil), p...))
	return len(p), nil
}

func (e *echoTunnel) Close() error {
	_ = e.w.Close()
	return e.r.Close()
}
