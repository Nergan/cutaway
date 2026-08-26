import 'dart:io';

import 'package:flutter/material.dart';

import '../application/usecases/connect_usecase.dart';
import '../application/usecases/disconnect_usecase.dart';
import '../application/usecases/enroll_usecase.dart';
import '../application/usecases/load_profile_usecase.dart';
import '../application/usecases/switch_node_usecase.dart';
import '../domain/ports/core_process_port.dart';
import '../infrastructure/api/config_repository_http_adapter.dart';
import '../infrastructure/core_bridge/http_core_adapter.dart';
import '../infrastructure/core_bridge/platform_channel_core_adapter.dart';
import '../infrastructure/storage/secure_profile_storage_adapter.dart';
import 'app_state.dart';
import 'screens/home/home_screen.dart';
import 'screens/onboarding/scan_invite_screen.dart';

/// Адрес локального control API core/cmd/desktop (см. §5.2 спецификации).
/// Переопределяется через `--dart-define=ANOTHER_LOCAL_API_URL=...` при
/// сборке — например, если Core запущен не на дефолтном порту.
const _localCoreApiUrl = String.fromEnvironment(
  'ANOTHER_LOCAL_API_URL',
  defaultValue: 'http://127.0.0.1:47821',
);

/// Директория хранения ключа устройства на мобильных платформах — должна
/// совпадать с тем, что нативный мост передаёт в mobilelib.Init (см.
/// PlatformChannelCoreAdapter). На практике на мобильных платформах чаще
/// используют путь, отдаваемый нативным слоем (Context.getFilesDir() и
/// т.п.) — здесь задан относительный дефолт, который нативный мост волен
/// переопределить своим абсолютным путём.
const _mobileKeyStoreDir = String.fromEnvironment(
  'ANOTHER_KEYSTORE_DIR',
  defaultValue: '.another/keystore',
);

/// Composition root Flutter-стороны (§6.1 спецификации) — единственное
/// место, где выбирается конкретный адаптер CoreProcessPort в зависимости
/// от платформы. Всё остальное дерево виджетов работает только через
/// AppState/use-cases, не зная деталей HTTP vs MethodChannel.
CoreProcessPort _buildCoreProcessPort() {
  if (Platform.isAndroid || Platform.isIOS) {
    return PlatformChannelCoreAdapter(keyStoreDir: _mobileKeyStoreDir);
  }
  return HttpCoreAdapter(baseUrl: _localCoreApiUrl);
}

class AnotherApp extends StatefulWidget {
  const AnotherApp({super.key});

  @override
  State<AnotherApp> createState() => _AnotherAppState();
}

class _AnotherAppState extends State<AnotherApp> {
  late final AppState appState;

  @override
  void initState() {
    super.initState();

    final core = _buildCoreProcessPort();
    final configRepository = ConfigRepositoryHttpAdapter();
    final profileStorage = SecureProfileStorageAdapter();

    appState = AppState(
      core: core,
      enrollUseCase: EnrollUseCase(
        core: core,
        configRepository: configRepository,
        profileStorage: profileStorage,
      ),
      connectUseCase: ConnectUseCase(core: core),
      disconnectUseCase: DisconnectUseCase(core: core),
      switchNodeUseCase: SwitchNodeUseCase(core: core, profileStorage: profileStorage),
      loadProfileUseCase: LoadProfileUseCase(profileStorage: profileStorage),
    );
    appState.bootstrap();
  }

  @override
  void dispose() {
    appState.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Another',
      debugShowCheckedModeBanner: false,
      // UI — только английский (см. app/README.md): экономия ресурсов на
      // необязательный функционал, приоритет — скорость, анонимизация
      // трафика, кроссплатформенность. Локализация намеренно не подключена.
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFF3562E3),
        brightness: Brightness.dark,
      ),
      home: ListenableBuilder(
        listenable: appState,
        builder: (context, _) {
          if (appState.profile == null) {
            return ScanInviteScreen(appState: appState);
          }
          return HomeScreen(appState: appState);
        },
      ),
    );
  }
}
