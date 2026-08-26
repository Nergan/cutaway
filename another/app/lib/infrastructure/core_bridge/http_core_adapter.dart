import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../domain/entities/node_descriptor.dart';
import '../../domain/entities/session_snapshot.dart';
import '../../domain/ports/core_process_port.dart';

/// HttpCoreAdapter — реализация CoreProcessPort для Windows/macOS/Linux,
/// через локальный loopback HTTP control API, который поднимает
/// core/cmd/desktop/main.go (§5.2 спецификации: TCP-loopback вместо unix
/// socket/named pipe — осознанный компромисс v1, см. core/README.md про
/// причины и план хардненинга в v2).
class HttpCoreAdapter implements CoreProcessPort {
  final String baseUrl;
  final http.Client _client;

  HttpCoreAdapter({required this.baseUrl, http.Client? client})
      : _client = client ?? http.Client();

  Map<String, dynamic> _decode(http.Response response) {
    final decoded = jsonDecode(response.body);
    if (decoded is! Map<String, dynamic>) {
      throw CoreProcessException('unexpected response shape from Core: ${response.body}');
    }
    return decoded;
  }

  void _throwIfNotOk(Map<String, dynamic> body, String fallbackMessage) {
    if (body['ok'] != true) {
      throw CoreProcessException(body['error'] as String? ?? fallbackMessage);
    }
  }

  @override
  Future<String> getOrCreatePublicKey() async {
    return (await getOrCreateDeviceKeys()).publicKeyHex;
  }

  @override
  Future<DevicePublicKeys> getOrCreateDeviceKeys() async {
    final response = await _client.get(Uri.parse('$baseUrl/identity'));
    final body = _decode(response);
    _throwIfNotOk(body, 'failed to obtain device public key');
    return DevicePublicKeys(
      publicKeyHex: body['public_key'] as String,
      publicKeyMldsa65Hex: body['public_key_mldsa65'] as String?,
    );
  }

  @override
  Future<void> connect({
    required String clientId,
    required List<NodeDescriptor> nodes,
    required String destHost,
    required int destPort,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/connect'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'client_id': clientId,
        'nodes': nodes.map((n) => n.toJson()).toList(),
        'dest_host': destHost,
        'dest_port': destPort,
      }),
    );
    _throwIfNotOk(_decode(response), 'connect failed');
  }

  @override
  Future<void> switchNode({
    required String clientId,
    required NodeDescriptor node,
    required String destHost,
    required int destPort,
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/switch'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode({
        'client_id': clientId,
        'node': node.toJson(),
        'dest_host': destHost,
        'dest_port': destPort,
      }),
    );
    _throwIfNotOk(_decode(response), 'switch node failed');
  }

  @override
  Future<void> disconnect() async {
    final response = await _client.post(Uri.parse('$baseUrl/disconnect'));
    _throwIfNotOk(_decode(response), 'disconnect failed');
  }

  @override
  Future<SessionSnapshot> status() async {
    final response = await _client.get(Uri.parse('$baseUrl/status'));
    return SessionSnapshot.fromJson(_decode(response));
  }
}
