import '../../domain/ports/core_process_port.dart';

class DisconnectUseCase {
  final CoreProcessPort core;
  const DisconnectUseCase({required this.core});

  Future<void> execute() => core.disconnect();
}
