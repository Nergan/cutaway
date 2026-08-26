import '../../domain/entities/profile.dart';
import '../../domain/ports/core_process_port.dart';

/// Пустой dest = VPN-режим ядра (TUN + NAT), не один заранее заданный хост.
const defaultDestHost = '';
const defaultDestPort = 0;

class ConnectUseCase {
  final CoreProcessPort core;
  const ConnectUseCase({required this.core});

  Future<void> execute(Profile profile) {
    return core.connect(
      clientId: profile.clientId,
      nodes: profile.nodes,
      destHost: defaultDestHost,
      destPort: defaultDestPort,
    );
  }
}
