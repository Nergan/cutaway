import 'dart:convert';

import 'package:flutter/services.dart';

import '../../domain/entities/node_descriptor.dart';
import '../../domain/entities/session_snapshot.dart';
import '../../domain/ports/core_process_port.dart';

/// PlatformChannelCoreAdapter — реализация CoreProcessPort для Android/iOS.
///
/// ПРАВКА относительно §5.2/§6.2 архитектурной спецификации (docs/architecture.md),
/// где мобильный мост был обозначен как "dart:ffi": на практике для связки
/// gomobile-собранной Go-библиотеки с Flutter надёжнее использовать
/// MethodChannel поверх тонкого нативного кода (Kotlin/Swift), а не сырой
/// dart:ffi + `-buildmode=c-shared`. Причина: `gomobile bind`
/// (см. core/cmd/mobilelib/binding.go) генерирует Java/Kotlin-классы
/// (Android, через JNI) и Swift/ObjC-заголовки (iOS) — а не плоский C ABI,
/// с которым dart:ffi работает "из коробки". Получить плоский C ABI можно
/// было бы через `-buildmode=c-shared`, но тогда пришлось бы вручную
/// писать JNI-обвязку под каждую архитектуру Android и заново решать то,
/// что `gomobile bind` уже решает. Этот же паттерн (gomobile bind + тонкий
/// нативный мост поверх MethodChannel) используется в большинстве реальных
/// Flutter+Go VPN-клиентов.
///
/// ЭТОТ АДАПТЕР НЕ РАБОТАЕТ БЕЗ:
///  1. Реально собранного `.aar` — `gomobile bind` у оператора
///     (`core/scripts/gomobile-android.sh`);
///  2. Клея в `app/native/android/` (AnotherCorePlugin + AnotherVpnService).
///     iOS вне релиза (ADR 0007).
///
/// Контракт со стороны Dart (имена методов канала и структура аргументов)
/// уже зафиксирован здесь и должен быть реализован нативным мостом 1-в-1 —
/// он полностью соответствует сигнатурам core/cmd/mobilelib/binding.go
/// (Init/Connect/Disconnect/Status/SwitchNode/GetPublicKey).
class PlatformChannelCoreAdapter implements CoreProcessPort {
  static const _channel = MethodChannel('another.core/control');

  final String keyStoreDir;

  PlatformChannelCoreAdapter({required this.keyStoreDir});

  Map<String, dynamic> _requireOk(Map<Object?, Object?>? result, String fallbackMessage) {
    if (result == null) {
      throw CoreProcessException('native bridge returned null');
    }
    final normalized = result.map((key, value) => MapEntry(key.toString(), value));
    if (normalized['ok'] != true) {
      throw CoreProcessException(normalized['error'] as String? ?? fallbackMessage);
    }
    return normalized;
  }

  @override
  Future<String> getOrCreatePublicKey() async {
    return (await getOrCreateDeviceKeys()).publicKeyHex;
  }

  @override
  Future<DevicePublicKeys> getOrCreateDeviceKeys() async {
    final result = await _channel.invokeMethod<Map<Object?, Object?>>(
      'getOrCreatePublicKey',
      {'keyStoreDir': keyStoreDir},
    );
    final body = _requireOk(result, 'failed to obtain device public key');
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
    // Нативный мост на первый вызов должен выполнить mobilelib.Init(clientId,
    // keyStoreDir, nodesJSON), а затем mobilelib.Connect(destHost, destPort)
    // (Init в Go идемпотентен через sync.Once — повторный вызов безопасен).
    final result = await _channel.invokeMethod<Map<Object?, Object?>>('connect', {
      'clientId': clientId,
      'keyStoreDir': keyStoreDir,
      'nodesJson': _encodeNodes(nodes),
      'destHost': destHost,
      'destPort': destPort,
    });
    _requireOk(result, 'connect failed');
  }

  @override
  Future<void> switchNode({
    required String clientId,
    required NodeDescriptor node,
    required String destHost,
    required int destPort,
  }) async {
    final result = await _channel.invokeMethod<Map<Object?, Object?>>('switchNode', {
      'nodeJson': _encodeNode(node),
      'destHost': destHost,
      'destPort': destPort,
    });
    _requireOk(result, 'switch node failed');
  }

  @override
  Future<void> disconnect() async {
    final result = await _channel.invokeMethod<Map<Object?, Object?>>('disconnect');
    _requireOk(result, 'disconnect failed');
  }

  @override
  Future<SessionSnapshot> status() async {
    final result = await _channel.invokeMethod<Map<Object?, Object?>>('status');
    if (result == null) {
      return SessionSnapshot.disconnected;
    }
    return SessionSnapshot.fromJson(result.map((key, value) => MapEntry(key.toString(), value)));
  }

  String _encodeNode(NodeDescriptor node) => jsonEncode(node.toJson());

  String _encodeNodes(List<NodeDescriptor> nodes) =>
      jsonEncode(nodes.map((n) => n.toJson()).toList());
}
