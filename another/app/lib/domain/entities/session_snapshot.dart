import 'vpn_session_state.dart';

/// SessionSnapshot — зеркало domain.Snapshot (Go, core/internal/domain/session.go)
/// и JSON-ответа GET /status (см. core/cmd/desktop/main.go, handleStatus).
class SessionSnapshot {
  final VpnSessionState state;
  final String? activeNodeName;
  final int bytesSent;
  final int bytesRecv;
  final String? lastError;

  const SessionSnapshot({
    required this.state,
    this.activeNodeName,
    this.bytesSent = 0,
    this.bytesRecv = 0,
    this.lastError,
  });

  static const disconnected = SessionSnapshot(state: VpnSessionState.disconnected);

  factory SessionSnapshot.fromJson(Map<String, dynamic> json) {
    return SessionSnapshot(
      state: VpnSessionState.fromWire(json['state'] as String?),
      activeNodeName: json['active_node'] as String?,
      bytesSent: (json['bytes_sent'] as num?)?.toInt() ?? 0,
      bytesRecv: (json['bytes_recv'] as num?)?.toInt() ?? 0,
      lastError: json['last_error'] as String?,
    );
  }
}
