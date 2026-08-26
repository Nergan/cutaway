import '../../domain/entities/profile.dart';
import '../../domain/ports/profile_storage_port.dart';

class LoadProfileUseCase {
  final ProfileStoragePort profileStorage;
  const LoadProfileUseCase({required this.profileStorage});

  Future<Profile?> execute() => profileStorage.loadProfile();
}
