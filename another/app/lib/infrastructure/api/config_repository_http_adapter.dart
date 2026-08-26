import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../domain/entities/node_descriptor.dart';
import '../../domain/ports/config_repository_port.dart';

/// ConfigRepositoryHttpAdapter — единственная реализация
/// ConfigRepositoryPort, обращается напрямую к edge/ (см.
/// edge/src/handlers/enroll.ts). Core в процессе онбординга нужен только
/// для генерации публичного ключа (CoreProcessPort.getOrCreatePublicKey) —
/// сам вызов /enroll делает Flutter напрямую по HTTP, без участия Core
/// (§6.1 спецификации: "обращается только к control-plane API").
class ConfigRepositoryHttpAdapter implements ConfigRepositoryPort {
  final http.Client _client;
  ConfigRepositoryHttpAdapter({http.Client? client}) : _client = client ?? http.Client();

  @override
  Future<EnrollmentResult> enroll({
    required String controlPlaneUrl,
    required String enrollmentToken,
    required String publicKeyHex,
    String? publicKeyMldsa65Hex,
  }) async {
    final response = await _client.post(
      Uri.parse('$controlPlaneUrl/enroll'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'enrollment_token': enrollmentToken,
        'public_key': publicKeyHex,
        if (publicKeyMldsa65Hex != null) 'public_key_mldsa65': publicKeyMldsa65Hex,
      }),
    );

    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw ConfigRepositoryException('unexpected response shape from edge/enroll: ${response.body}');
    }

    if (response.statusCode != 200 || decoded['ok'] != true) {
      throw ConfigRepositoryException(
        decoded['error'] as String? ?? 'enrollment failed (HTTP ${response.statusCode})',
      );
    }

    final nodesJson = decoded['nodes'] as List<dynamic>? ?? const [];
    final nodes = nodesJson
        .map((e) => NodeDescriptor.fromJson(
              e as Map<String, dynamic>,
              controlPlaneFallback: controlPlaneUrl,
            ))
        .toList();

    return EnrollmentResult(
      clientId: decoded['client_id'] as String,
      vlessUserId: decoded['vless_user_id'] as String,
      nodes: nodes,
    );
  }
}
