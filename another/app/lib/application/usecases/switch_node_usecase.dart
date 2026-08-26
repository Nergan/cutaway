import '../../domain/entities/node_descriptor.dart';
import '../../domain/entities/profile.dart';
import '../../domain/ports/core_process_port.dart';
import '../../domain/ports/profile_storage_port.dart';
import 'connect_usecase.dart' show defaultDestHost, defaultDestPort;

/// SwitchNodeUseCase — ручное переключение узла из UI (см.
/// core/internal/app/switch_node_usecase.go — тот же принцип на стороне
/// Core: kill switch остаётся armed на протяжении всего переключения).
/// Дополнительно обновляет локальный профиль, чтобы выбранный узел
/// оставался первым по приоритету и при следующем обычном Connect().
class SwitchNodeUseCase {
  final CoreProcessPort core;
  final ProfileStoragePort profileStorage;

  const SwitchNodeUseCase({required this.core, required this.profileStorage});

  Future<Profile> execute(Profile profile, NodeDescriptor target) async {
    await core.switchNode(
      clientId: profile.clientId,
      node: target,
      destHost: defaultDestHost,
      destPort: defaultDestPort,
    );

    final updated = profile.withNodePromoted(target);
    await profileStorage.saveProfile(updated);
    return updated;
  }
}
