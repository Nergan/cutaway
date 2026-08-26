import 'package:flutter/foundation.dart';

import '../application/usecases/connect_usecase.dart';
import '../application/usecases/disconnect_usecase.dart';
import '../application/usecases/enroll_usecase.dart';
import '../application/usecases/load_profile_usecase.dart';
import '../application/usecases/switch_node_usecase.dart';
import '../domain/entities/node_descriptor.dart';
import '../domain/entities/profile.dart';
import '../domain/entities/session_snapshot.dart';
import '../domain/ports/core_process_port.dart';

/// AppState — единственный ChangeNotifier верхнего уровня. Каждый публичный
/// метод — тонкая обёртка над одним use-case; ни один виджет не обращается
/// ни к одному адаптеру напрямую (границы гексагональной архитектуры
/// соблюдаются и на уровне GUI, а не только в core/edge/control-plane-admin).
class AppState extends ChangeNotifier {
  final EnrollUseCase enrollUseCase;
  final ConnectUseCase connectUseCase;
  final DisconnectUseCase disconnectUseCase;
  final SwitchNodeUseCase switchNodeUseCase;
  final LoadProfileUseCase loadProfileUseCase;
  final CoreProcessPort core;

  Profile? profile;
  SessionSnapshot snapshot = SessionSnapshot.disconnected;
  String? lastError;
  bool isBusy = false;

  AppState({
    required this.enrollUseCase,
    required this.connectUseCase,
    required this.disconnectUseCase,
    required this.switchNodeUseCase,
    required this.loadProfileUseCase,
    required this.core,
  });

  Future<void> bootstrap() async {
    profile = await loadProfileUseCase.execute();
    notifyListeners();
    if (profile != null) {
      await refreshStatus();
    }
  }

  Future<void> refreshStatus() async {
    try {
      snapshot = await core.status();
    } catch (_) {
      // Core может быть ещё не запущен (напр. на десктопе — до старта
      // локального control API) — это не повод показывать ошибку сразу
      // после запуска приложения, статус просто останется "disconnected".
    }
    notifyListeners();
  }

  Future<void> enroll({
    required String controlPlaneUrl,
    required String enrollmentToken,
  }) async {
    await _runBusy(() async {
      profile = await enrollUseCase.execute(
        controlPlaneUrl: controlPlaneUrl,
        enrollmentToken: enrollmentToken,
      );
    });
  }

  Future<void> connect() async {
    final currentProfile = profile;
    if (currentProfile == null) return;
    await _runBusy(() => connectUseCase.execute(currentProfile));
    await refreshStatus();
  }

  Future<void> disconnect() async {
    await _runBusy(disconnectUseCase.execute);
    await refreshStatus();
  }

  Future<void> switchToNode(NodeDescriptor node) async {
    final currentProfile = profile;
    if (currentProfile == null) return;
    await _runBusy(() async {
      profile = await switchNodeUseCase.execute(currentProfile, node);
    });
    await refreshStatus();
  }

  Future<void> _runBusy(Future<void> Function() action) async {
    isBusy = true;
    lastError = null;
    notifyListeners();
    try {
      await action();
    } catch (e) {
      lastError = e.toString();
    } finally {
      isBusy = false;
      notifyListeners();
    }
  }
}
