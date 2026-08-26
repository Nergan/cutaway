import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

import '../../domain/entities/profile.dart';
import '../../domain/ports/profile_storage_port.dart';

/// SecureProfileStorageAdapter — хранит Profile (client_id, control-plane
/// URL, узлы) в защищённом хранилище платформы (Keychain на iOS/macOS,
/// Keystore-backed EncryptedSharedPreferences на Android, DPAPI на Windows,
/// libsecret на Linux — всё это уже инкапсулировано пакетом
/// flutter_secure_storage). НЕ хранит приватный ключ устройства — тот
/// целиком управляется Core (см. core/internal/adapters/keystore/file_keystore.go),
/// сюда попадают только несекретные по сути (но всё равно не публикуемые
/// без нужды) метаданные профиля.
class SecureProfileStorageAdapter implements ProfileStoragePort {
  static const _key = 'another_profile_v1';
  final FlutterSecureStorage _storage;

  SecureProfileStorageAdapter({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  @override
  Future<Profile?> loadProfile() async {
    final raw = await _storage.read(key: _key);
    if (raw == null) return null;
    return Profile.fromJson(jsonDecode(raw) as Map<String, dynamic>);
  }

  @override
  Future<void> saveProfile(Profile profile) async {
    await _storage.write(key: _key, value: jsonEncode(profile.toJson()));
  }

  @override
  Future<void> clearProfile() async {
    await _storage.delete(key: _key);
  }
}
