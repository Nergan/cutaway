/// Значения тегов Tier — тот же текстовый вид, что у Tier.String() в
/// core/internal/domain/node.go и в edge/wrangler.toml (NODES_JSON).
abstract final class NodeTier {
  static const tier1Bootstrap = 'tier1-bootstrap';
  static const tier2Target = 'tier2-target';
}

/// Значения тегов транспорта — тот же текстовый вид, что у
/// TransportKind.String() в core/internal/domain/node.go.
abstract final class TransportKind {
  static const vlessWs = 'vless-ws';
  static const vlessGrpc = 'vless-grpc';
  static const vlessReality = 'vless-reality';
  static const echo = 'echo';
}

/// NodeDescriptor — зеркало domain.NodeDescriptor (Go) и формата, который
/// отдаёт edge/src/handlers/enroll.ts. JSON-теги совпадают буква в букву
/// (snake_case), чтобы один и тот же объект без конвертации проходил путь
/// edge/ → Flutter → Core (см. core/internal/domain/node.go, комментарий
/// про единый формат на всех трёх границах).
class NodeDescriptor {
  final String name;
  final String tier;
  final String transport;
  final String host;
  final int port;
  final String path;
  final String? sni;
  final int priority;
  final String controlPlane;

  const NodeDescriptor({
    required this.name,
    required this.tier,
    required this.transport,
    required this.host,
    required this.port,
    required this.path,
    this.sni,
    required this.priority,
    required this.controlPlane,
  });

  /// controlPlaneFallback — edge/enroll не включает control_plane в каждый
  /// узел (все Tier1-узлы используют ОДИН и тот же control-plane — сам
  /// Cloudflare Worker, к которому уже шёл запрос /enroll), поэтому при
  /// отсутствии поля в JSON используется URL, которым мы уже
  /// воспользовались для регистрации устройства.
  factory NodeDescriptor.fromJson(
    Map<String, dynamic> json, {
    required String controlPlaneFallback,
  }) {
    return NodeDescriptor(
      name: json['name'] as String,
      tier: json['tier'] as String,
      transport: json['transport'] as String,
      host: json['host'] as String,
      port: (json['port'] as num).toInt(),
      path: json['path'] as String? ?? '/',
      sni: json['sni'] as String?,
      priority: (json['priority'] as num?)?.toInt() ?? 0,
      controlPlane: json['control_plane'] as String? ?? controlPlaneFallback,
    );
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'tier': tier,
        'transport': transport,
        'host': host,
        'port': port,
        'path': path,
        if (sni != null) 'sni': sni,
        'priority': priority,
        'control_plane': controlPlane,
      };

  /// withPriority — используется при переключении узла из UI: копия узла с
  /// изменённым приоритетом, без мутации исходного (все entities immutable).
  NodeDescriptor withPriority(int newPriority) => NodeDescriptor(
        name: name,
        tier: tier,
        transport: transport,
        host: host,
        port: port,
        path: path,
        sni: sni,
        priority: newPriority,
        controlPlane: controlPlane,
      );
}
