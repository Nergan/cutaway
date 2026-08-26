import '../entities/node_descriptor.dart';

class EnrollmentResult {
  final String clientId;
  final String vlessUserId;
  final List<NodeDescriptor> nodes;

  const EnrollmentResult({
    required this.clientId,
    required this.vlessUserId,
    required this.nodes,
  });
}

class ConfigRepositoryException implements Exception {
  final String message;
  const ConfigRepositoryException(this.message);

  @override
  String toString() => 'ConfigRepositoryException: $message';
}

/// ConfigRepositoryPort — driven-порт к control-plane (edge/). Обращается
/// ИСКЛЮЧИТЕЛЬНО к HTTP API edge/, никогда напрямую к MongoDB (§6.1
/// спецификации) — единственная реализация,
/// infrastructure/api/config_repository_http_adapter.dart, вызывает
/// edge/src/handlers/enroll.ts.
abstract interface class ConfigRepositoryPort {
  Future<EnrollmentResult> enroll({
    required String controlPlaneUrl,
    required String enrollmentToken,
    required String publicKeyHex,
    String? publicKeyMldsa65Hex,
  });
}
