// cmd/desktop — composition root для Windows/macOS/Linux (см. §5.2
// спецификации). Это единственное место в проекте, где конкретные адаптеры
// связываются с портами — весь остальной код (domain, ports, app) ничего не
// знает о том, что используется именно FileKeyStore или именно
// VLESSWebSocketTransport.
//
// Flutter на десктопе управляет жизненным циклом этого процесса и общается
// с ним через простой JSON HTTP API на loopback-адресе (POST /connect,
// POST /disconnect, GET /status) — см. ADR в internal/config: в v1 сознательно
// выбран TCP-loopback вместо unix socket/named pipe, чтобы не иметь
// платформенно-разного кода на этом уровне (именованные пайпы Windows
// требуют доп. библиотеку github.com/Microsoft/go-winio, недоступную без
// module proxy). Хардننг до unix socket/named pipe — в v2, см. README.md.
package main

import (
	"context"
	"encoding/json"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"path/filepath"
	"strings"

	"github.com/another-vpn/another/core/internal/adapters/auth"
	"github.com/another-vpn/another/core/internal/adapters/enroll"
	"github.com/another-vpn/another/core/internal/adapters/keystore"
	"github.com/another-vpn/another/core/internal/adapters/killswitch"
	"github.com/another-vpn/another/core/internal/adapters/probe"
	"github.com/another-vpn/another/core/internal/adapters/provisioning"
	"github.com/another-vpn/another/core/internal/adapters/ratelimiter"
	"github.com/another-vpn/another/core/internal/adapters/transport"
	"github.com/another-vpn/another/core/internal/adapters/tun"
	"github.com/another-vpn/another/core/internal/app"
	"github.com/another-vpn/another/core/internal/bootstrap"
	"github.com/another-vpn/another/core/internal/config"
	"github.com/another-vpn/another/core/internal/domain"
	"github.com/another-vpn/another/core/internal/ports"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))

	_ = config.LoadDotEnv(".env")
	_ = config.LoadDotEnv(filepath.Join("..", ".env"))
	_ = config.LoadDotEnv(filepath.Join("..", "..", ".env"))
	cfg := config.Load()

	logger.Info("starting another-core (desktop)",
		"client_id", cfg.ClientID,
		"control_plane", cfg.ControlPlaneURL,
		"local_api", cfg.LocalAPIAddr,
	)

	// --- Composition root: связываем порты с конкретными адаптерами ---
	session := domain.NewTunnelSession()
	ks := keystore.NewFileKeyStore(cfg.KeyStoreDir)
	authAdapter := auth.NewHTTPChallengeAdapter()
	muxTransport := transport.NewMuxTransport()
	tunAdapter := tun.SelectTun(logger)
	killSwitch := killswitch.SelectKillSwitch(logger)
	limiter := ratelimiter.NewTokenBucket(1_250_000, 2_000_000)

	bundle := provisioning.Load()
	clientID := cfg.ClientID
	if bundle.ClientID != "" {
		clientID = bundle.ClientID
	}

	policy := domain.NewFailoverPolicy(defaultNodes(cfg))
	if len(bundle.Entrypoints) > 0 {
		policy = domain.NewFailoverPolicy(bundle.Entrypoints)
	}

	prepared, prepErr := bootstrap.PrepareSession(context.Background(), logger, ks, enroll.New(), cfg.KeyStoreDir, bundle, cfg.ControlPlaneURL)
	if prepErr != nil {
		logger.Error("auto-start prepare failed", "error", prepErr)
	} else {
		if prepared.ClientID != "" {
			clientID = prepared.ClientID
		}
		if prepared.Policy != nil && len(prepared.Policy.Ordered()) > 0 {
			policy = prepared.Policy
		}
	}

	connectUC := app.NewConnectUseCase(session, ks, authAdapter, muxTransport, tunAdapter, killSwitch, limiter, clientID, logger)
	connectUC.Prober = probe.NewTCPProber()
	disconnectUC := app.NewDisconnectUseCase(session, tunAdapter, killSwitch, logger)
	switchUC := app.NewSwitchNodeUseCase(session, ks, authAdapter, muxTransport, tunAdapter, clientID, logger)

	if prepared.AutoConnect && prepared.Policy != nil && os.Getenv("ANOTHER_SKIP_AUTO_START") != "1" {
		go func() {
			logger.Info("auto-connect")
			if err := connectUC.Execute(context.Background(), prepared.Policy, "", 0); err != nil {
				logger.Error("auto-connect failed", "error", err)
			}
		}()
	}

	srv := newControlServer(connectUC, disconnectUC, switchUC, session, policy, ks, logger)
	go func() {
		ch := make(chan os.Signal, 1)
		signal.Notify(ch, os.Interrupt)
		<-ch
		logger.Info("interrupt, disconnecting")
		_ = disconnectUC.Execute(context.Background())
		os.Exit(0)
	}()
	logger.Info("local control API listening", "addr", cfg.LocalAPIAddr)
	if err := http.ListenAndServe(cfg.LocalAPIAddr, srv); err != nil {
		logger.Error("control API server failed", "error", err)
		os.Exit(1)
	}
}

func defaultNodes(cfg config.Config) []domain.NodeDescriptor {
	return []domain.NodeDescriptor{
		{
			Name: "cf-worker", Tier: domain.Tier1Bootstrap, Transport: domain.TransportVLESSWebSocket,
			Host: mustEnv("ANOTHER_NODE_CF_HOST", "cf-worker.another.example"), Port: 443, Path: "/proxy",
			ControlPlane: cfg.ControlPlaneURL, Priority: 1,
		},
		{
			Name: "hf-xhttp", Tier: domain.Tier1Bootstrap, Transport: domain.TransportVLESSXHTTP,
			Host: mustEnv("ANOTHER_NODE_HF_HOST", "CHANGE_ME.hf.space"), Port: 443, Path: "/xhttp",
			ControlPlane: cfg.ControlPlaneURL, Priority: 2,
		},
		{
			Name: "render", Tier: domain.Tier1Bootstrap, Transport: domain.TransportVLESSWebSocket,
			Host: mustEnv("ANOTHER_NODE_RENDER_HOST", "another-backup.onrender.com"), Port: 443, Path: "/proxy",
			ControlPlane: cfg.ControlPlaneURL, Priority: 3,
		},
	}
}

func mustEnv(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

// controlServer — тонкий JSON HTTP API поверх use-cases. Это driving-адаптер
// со стороны Flutter (аналог CoreControlPort из §5.1 спецификации, только
// вместо FFI — loopback HTTP, что проще для v1 на десктопе).
type controlServer struct {
	mux *http.ServeMux

	connect    *app.ConnectUseCase
	disconnect *app.DisconnectUseCase
	switchNode *app.SwitchNodeUseCase
	session    *domain.TunnelSession
	policy     *domain.FailoverPolicy
	keyStore   ports.KeyStorePort
	logger     *slog.Logger
}

func newControlServer(connect *app.ConnectUseCase, disconnect *app.DisconnectUseCase, switchNode *app.SwitchNodeUseCase, session *domain.TunnelSession, policy *domain.FailoverPolicy, keyStore ports.KeyStorePort, logger *slog.Logger) *controlServer {
	s := &controlServer{
		mux: http.NewServeMux(), connect: connect, disconnect: disconnect,
		switchNode: switchNode, session: session, policy: policy, keyStore: keyStore, logger: logger,
	}
	s.mux.HandleFunc("/connect", s.handleConnect)
	s.mux.HandleFunc("/disconnect", s.handleDisconnect)
	s.mux.HandleFunc("/status", s.handleStatus)
	s.mux.HandleFunc("/identity", s.handleIdentity)
	s.mux.HandleFunc("/switch", s.handleSwitch)
	return s
}

func (s *controlServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	s.mux.ServeHTTP(w, r)
}

type connectRequest struct {
	DestHost string `json:"dest_host"`
	DestPort uint16 `json:"dest_port"`
	// ClientID — опциональное переопределение серверного client_id,
	// полученного Flutter при онбординге (§7.1). Без него используется
	// статическое значение ANOTHER_CLIENT_ID из окружения (полезно для
	// одиночного запуска Core без GUI). ClientID на старте процесса (в
	// main()) неизбежно ещё не может быть "настоящим" — онбординг
	// происходит уже после старта Core, поэтому единственный способ
	// сообщить реальный client_id — передать его сюда.
	//
	// ПРИМЕЧАНИЕ: мутация полей use-case здесь предполагает, что
	// локальный control API обслуживает ровно один GUI-процесс на
	// устройстве последовательными запросами — не потокобезопасно при
	// параллельных вызовах, что для v1 (один Flutter-клиент на инстанс
	// Core) достаточно.
	ClientID string `json:"client_id,omitempty"`
	// Nodes — JSON массива или одного объекта (PowerShell 5.1 сворачивает
	// одноэлементный массив). Если поле пустое, берётся политика из env;
	// для смоук-теста шага 7 сюда нужно передать $enroll.nodes.
	Nodes json.RawMessage `json:"nodes,omitempty"`
}

func (s *controlServer) handleConnect(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req connectRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	// dest_host пустой = полноценный VPN (TUN). Не подставляем example.com.

	nodes, err := domain.ParseNodeList(req.Nodes)
	if err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	policy := s.policy
	if len(nodes) > 0 {
		policy = domain.NewFailoverPolicy(nodes)
	} else if policyUsesLoopbackControlPlane(s.policy) {
		writeJSON(w, http.StatusOK, map[string]any{
			"ok": false,
			"error": "nodes required: pass $enroll.nodes from POST /enroll. " +
				"Without it the core uses ANOTHER_CONTROL_PLANE_URL, default http://127.0.0.1:8787 (wrangler dev).",
		})
		return
	}
	if req.ClientID != "" {
		s.connect.ClientID = req.ClientID
		s.switchNode.ClientID = req.ClientID
	}
	if clientID := strings.TrimSpace(s.connect.ClientID); clientID == "" || clientID == "dev-device" {
		writeJSON(w, http.StatusOK, map[string]any{
			"ok": false,
			"error": "client_id is empty (PowerShell lost $enroll). " +
				"Copy the ENROLLED client_id from the admin panel, or re-run step 6 in this window.",
		})
		return
	}
	if policyUsesLoopbackControlPlane(policy) {
		writeJSON(w, http.StatusOK, map[string]any{
			"ok": false,
			"error": "control_plane is wrangler dev (127.0.0.1:8787). " +
				"Enroll against the production worker and set nodes[].control_plane to $WORKER, " +
				"or set ANOTHER_CONTROL_PLANE_URL before starting another-core.exe.",
		})
		return
	}

	if err := s.connect.Execute(r.Context(), policy, req.DestHost, req.DestPort); err != nil {
		s.logger.Error("connect failed", "error", err)
		writeJSON(w, http.StatusOK, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (s *controlServer) handleDisconnect(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	if err := s.disconnect.Execute(r.Context()); err != nil {
		writeJSON(w, http.StatusOK, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func (s *controlServer) handleStatus(w http.ResponseWriter, r *http.Request) {
	snap := s.session.Snapshot()
	resp := map[string]any{
		"state":      snap.State.String(),
		"bytes_sent": snap.BytesSent,
		"bytes_recv": snap.BytesRecv,
	}
	if snap.ActiveNode != nil {
		resp["active_node"] = snap.ActiveNode.Name
	}
	if snap.LastError != nil {
		resp["last_error"] = snap.LastError.Error()
	}
	writeJSON(w, http.StatusOK, resp)
}

// handleIdentity — GET /identity. Возвращает (создавая при первом вызове)
// публичный ключ устройства, ДО того как известен серверный client_id —
// именно это нужно Flutter-слою на экране онбординга перед вызовом
// edge/enroll (§7.1 спецификации, см. также комментарий в
// domain.DeviceIdentity про порядок операций).
func (s *controlServer) handleIdentity(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	identity, err := s.keyStore.LoadOrCreateDeviceIdentity()
	if err != nil {
		s.logger.Error("load identity failed", "error", err)
		writeJSON(w, http.StatusInternalServerError, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"ok":                 true,
		"public_key":         identity.PublicKeyHex(),
		"public_key_mldsa65": identity.MLDSAPublicKeyHex(),
	})
}

type switchRequest struct {
	ClientID string                `json:"client_id,omitempty"`
	Node     domain.NodeDescriptor `json:"node"`
	DestHost string                `json:"dest_host"`
	DestPort uint16                `json:"dest_port"`
}

// handleSwitch — POST /switch. В отличие от повторного POST /connect,
// использует app.SwitchNodeUseCase: держит kill switch armed на протяжении
// всего переключения и корректно закрывает старый туннель перед открытием
// нового (см. §5.4 спецификации и internal/app/switch_node_usecase.go).
func (s *controlServer) handleSwitch(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
		return
	}
	var req switchRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		http.Error(w, "invalid request body", http.StatusBadRequest)
		return
	}
	if req.DestHost == "" {
		req.DestHost = "example.com"
	}
	if req.DestPort == 0 {
		req.DestPort = 443
	}
	if req.ClientID != "" {
		s.switchNode.ClientID = req.ClientID
	}

	if err := s.switchNode.Execute(r.Context(), req.Node, req.DestHost, req.DestPort); err != nil {
		s.logger.Error("switch node failed", "error", err)
		writeJSON(w, http.StatusOK, map[string]any{"ok": false, "error": err.Error()})
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{"ok": true})
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func policyUsesLoopbackControlPlane(p *domain.FailoverPolicy) bool {
	if p == nil {
		return false
	}
	for _, n := range p.Ordered() {
		u := strings.ToLower(n.ControlPlane)
		if strings.Contains(u, "127.0.0.1") || strings.Contains(u, "localhost") || strings.Contains(u, "[::1]") {
			return true
		}
	}
	return false
}
