import '../../domain/entities/profile.dart';
import '../../domain/ports/config_repository_port.dart';
import '../../domain/ports/core_process_port.dart';
import '../../domain/ports/profile_storage_port.dart';

/// EnrollUseCase — прямой перенос последовательности §7.1 спецификации:
///   1. получить публичный ключ от Core (клиентский client_id ещё не известен);
///   2. обменять его вместе с enrollment_token на привязку через edge/enroll;
///   3. сохранить результат как локальный профиль.
class EnrollUseCase {
  final CoreProcessPort core;
  final ConfigRepositoryPort configRepository;
  final ProfileStoragePort profileStorage;

  const EnrollUseCase({
    required this.core,
    required this.configRepository,
    required this.profileStorage,
  });

  Future<Profile> execute({
    required String controlPlaneUrl,
    required String enrollmentToken,
  }) async {
    final keys = await core.getOrCreateDeviceKeys();

    final result = await configRepository.enroll(
      controlPlaneUrl: controlPlaneUrl,
      enrollmentToken: enrollmentToken,
      publicKeyHex: keys.publicKeyHex,
      publicKeyMldsa65Hex: keys.publicKeyMldsa65Hex,
    );

    final profile = Profile(
      clientId: result.clientId,
      controlPlaneUrl: controlPlaneUrl,
      nodes: result.nodes,
      enrolledAt: DateTime.now(),
    );

    await profileStorage.saveProfile(profile);
    return profile;
  }
}
