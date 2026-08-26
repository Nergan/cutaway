import 'package:flutter_test/flutter_test.dart';

import 'package:another/domain/entities/node_descriptor.dart';
import 'package:another/domain/entities/profile.dart';

void main() {
  group('NodeDescriptor', () {
    test('fromJson uses control_plane from JSON when present', () {
      final node = NodeDescriptor.fromJson(
        {
          'name': 'cf-worker',
          'tier': NodeTier.tier1Bootstrap,
          'transport': TransportKind.vlessWs,
          'host': 'cf-worker.another.example',
          'port': 443,
          'path': '/proxy',
          'priority': 1,
          'control_plane': 'https://explicit.example',
        },
        controlPlaneFallback: 'https://fallback.example',
      );

      expect(node.controlPlane, 'https://explicit.example');
    });

    test('fromJson falls back to controlPlaneFallback when control_plane is absent', () {
      // Соответствует формату ответа edge/src/handlers/enroll.ts — узлы там
      // НЕ включают control_plane (все Tier1-узлы используют общий
      // control-plane, см. app/lib/domain/entities/node_descriptor.dart).
      final node = NodeDescriptor.fromJson(
        {
          'name': 'render',
          'tier': NodeTier.tier1Bootstrap,
          'transport': TransportKind.vlessWs,
          'host': 'another-backup.onrender.com',
          'port': 443,
          'path': '/proxy',
          'priority': 2,
        },
        controlPlaneFallback: 'https://fallback.example',
      );

      expect(node.controlPlane, 'https://fallback.example');
    });

    test('toJson/fromJson round-trip preserves all fields', () {
      const original = NodeDescriptor(
        name: 'vps-reality',
        tier: NodeTier.tier2Target,
        transport: TransportKind.vlessReality,
        host: '1.2.3.4',
        port: 443,
        path: '/',
        sni: 'donor.example',
        priority: 0,
        controlPlane: 'https://cf-worker.another.example',
      );

      final decoded = NodeDescriptor.fromJson(
        original.toJson(),
        controlPlaneFallback: 'should-not-be-used',
      );

      expect(decoded.name, original.name);
      expect(decoded.tier, original.tier);
      expect(decoded.transport, original.transport);
      expect(decoded.host, original.host);
      expect(decoded.port, original.port);
      expect(decoded.sni, original.sni);
      expect(decoded.controlPlane, original.controlPlane);
    });

    test('withPriority returns a new instance without mutating the original', () {
      const original = NodeDescriptor(
        name: 'a',
        tier: NodeTier.tier1Bootstrap,
        transport: TransportKind.vlessWs,
        host: 'a.example',
        port: 443,
        path: '/',
        priority: 5,
        controlPlane: 'https://cp.example',
      );

      final promoted = original.withPriority(0);

      expect(original.priority, 5);
      expect(promoted.priority, 0);
      expect(promoted.name, original.name);
    });
  });

  group('Profile.withNodePromoted', () {
    const cfWorker = NodeDescriptor(
      name: 'cf-worker',
      tier: NodeTier.tier1Bootstrap,
      transport: TransportKind.vlessWs,
      host: 'a.example',
      port: 443,
      path: '/',
      priority: 1,
      controlPlane: 'https://cp.example',
    );
    const render = NodeDescriptor(
      name: 'render',
      tier: NodeTier.tier1Bootstrap,
      transport: TransportKind.vlessWs,
      host: 'b.example',
      port: 443,
      path: '/',
      priority: 2,
      controlPlane: 'https://cp.example',
    );

    final profile = Profile(
      clientId: 'test-client',
      controlPlaneUrl: 'https://cp.example',
      nodes: [cfWorker, render],
      enrolledAt: DateTime.utc(2026, 1, 1),
    );

    test('promoted node becomes first with priority 0', () {
      final updated = profile.withNodePromoted(render);

      expect(updated.nodes.first.name, 'render');
      expect(updated.nodes.first.priority, 0);
    });

    test('other nodes are kept, re-numbered, and not duplicated', () {
      final updated = profile.withNodePromoted(render);

      expect(updated.nodes.length, 2);
      expect(updated.nodes.map((n) => n.name).toSet(), {'cf-worker', 'render'});
      expect(updated.nodes.last.name, 'cf-worker');
      expect(updated.nodes.last.priority, 1);
    });

    test('promoting the already-first node is a no-op in terms of membership', () {
      final updated = profile.withNodePromoted(cfWorker);
      expect(updated.nodes.map((n) => n.name).toList(), ['cf-worker', 'render']);
    });

    test('original profile is not mutated', () {
      profile.withNodePromoted(render);
      expect(profile.nodes.first.name, 'cf-worker'); // исходный порядок сохранён
    });
  });
}
