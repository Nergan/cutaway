import '../entities/node_descriptor.dart';
import '../entities/session_snapshot.dart';

class DevicePublicKeys {
  final String publicKeyHex;
  final String? publicKeyMldsa65Hex;

  const DevicePublicKeys({required this.publicKeyHex, this.publicKeyMldsa65Hex});
}

/// CoreProcessException — единый тип ошибки для всех реализаций
/// CoreProcessPort (используется и HttpCoreAdapter, и
/// PlatformChannelCoreAdapter — вынесен сюда, а не дублируется в каждом
/// адаптере, чтобы presentation-слой мог ловить один тип независимо от
/// платформы).
class CoreProcessException implements Exception {
  final String message;
  const CoreProcessException(this.message);

  @override
  String toString() => 'CoreProcessException: $message';
}

/// CoreProcessPort — driven-порт к Go-ядру (core/), см. §6.1 спецификации.
/// Два адаптера в infrastructure/core_bridge/:
///   - HttpCoreAdapter — десктоп (Windows/macOS/Linux), через локальный
///     loopback control API (см. core/cmd/desktop/main.go).
///   - PlatformChannelCoreAdapter — Android/iOS, через нативный мост поверх
///     gomobile-биндинга (см. core/cmd/mobilelib/binding.go и комментарий
///     в самом адаптере про то, почему не сырой dart:ffi).
abstract interface class CoreProcessPort {
  /// Публичный ключ устройства — создаётся при первом вызове, если ещё не
  /// существует. Вызывается ДО онбординга (§7.1: порядок операций —
  /// сначала ключ, потом /enroll, потом уже известен серверный client_id).
  Future<String> getOrCreatePublicKey();

  Future<DevicePublicKeys> getOrCreateDeviceKeys();

  Future<void> connect({
    required String clientId,
    required List<NodeDescriptor> nodes,
    required String destHost,
    required int destPort,
  });

  Future<void> switchNode({
    required String clientId,
    required NodeDescriptor node,
    required String destHost,
    required int destPort,
  });

  Future<void> disconnect();

  Future<SessionSnapshot> status();
}
