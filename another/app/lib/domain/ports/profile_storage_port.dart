import '../entities/profile.dart';

/// ProfileStoragePort — driven-порт для локального хранения профиля
/// (client_id, control-plane URL, узлы — НЕ приватный ключ, см.
/// domain/entities/profile.dart). Реализация —
/// infrastructure/storage/secure_profile_storage_adapter.dart.
abstract interface class ProfileStoragePort {
  Future<Profile?> loadProfile();
  Future<void> saveProfile(Profile profile);
  Future<void> clearProfile();
}
