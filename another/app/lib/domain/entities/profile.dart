import 'node_descriptor.dart';

/// Profile — то, что приложение хранит локально после успешного онбординга
/// (§7.1 спецификации). НЕ содержит приватный ключ устройства (тот остаётся
/// исключительно в Core, см. core/internal/adapters/keystore/file_keystore.go)
/// — только серверный client_id и список известных узлов, чего достаточно
/// для последующих Connect()/SwitchNode() вызовов.
class Profile {
  final String clientId;
  final String controlPlaneUrl;
  final List<NodeDescriptor> nodes;
  final DateTime enrolledAt;

  const Profile({
    required this.clientId,
    required this.controlPlaneUrl,
    required this.nodes,
    required this.enrolledAt,
  });

  factory Profile.fromJson(Map<String, dynamic> json) {
    final controlPlaneUrl = json['control_plane_url'] as String;
    final nodesJson = json['nodes'] as List<dynamic>? ?? const [];
    return Profile(
      clientId: json['client_id'] as String,
      controlPlaneUrl: controlPlaneUrl,
      nodes: nodesJson
          .map((e) => NodeDescriptor.fromJson(
                e as Map<String, dynamic>,
                controlPlaneFallback: controlPlaneUrl,
              ))
          .toList(),
      enrolledAt: DateTime.parse(json['enrolled_at'] as String),
    );
  }

  Map<String, dynamic> toJson() => {
        'client_id': clientId,
        'control_plane_url': controlPlaneUrl,
        'nodes': nodes.map((n) => n.toJson()).toList(),
        'enrolled_at': enrolledAt.toIso8601String(),
      };

  /// withNodesReorderedFirst — новый Profile с указанным узлом на первом
  /// месте по приоритету (используется при ручном переключении узла из UI,
  /// см. presentation/screens/node_picker/node_picker_screen.dart).
  Profile withNodePromoted(NodeDescriptor promoted) {
    final reordered = <NodeDescriptor>[];
    var nextPriority = 0;
    reordered.add(promoted.withPriority(nextPriority++));
    for (final n in nodes) {
      if (n.name != promoted.name) {
        reordered.add(n.withPriority(nextPriority++));
      }
    }
    return Profile(
      clientId: clientId,
      controlPlaneUrl: controlPlaneUrl,
      nodes: reordered,
      enrolledAt: enrolledAt,
    );
  }
}
