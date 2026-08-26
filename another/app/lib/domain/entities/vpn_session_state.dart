/// VpnSessionState — зеркало domain.SessionState из core/internal/domain/session.go
/// и state в JSON-ответе GET /status (см. core/cmd/desktop/main.go).
enum VpnSessionState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  failed;

  static VpnSessionState fromWire(String? value) {
    switch (value) {
      case 'connecting':
        return VpnSessionState.connecting;
      case 'connected':
        return VpnSessionState.connected;
      case 'reconnecting':
        return VpnSessionState.reconnecting;
      case 'failed':
        return VpnSessionState.failed;
      case 'disconnected':
      default:
        return VpnSessionState.disconnected;
    }
  }
}
