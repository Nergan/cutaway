import 'package:flutter/material.dart';

import '../../domain/entities/vpn_session_state.dart';

class ConnectButton extends StatelessWidget {
  final VpnSessionState state;
  final bool busy;
  final VoidCallback onConnect;
  final VoidCallback onDisconnect;

  const ConnectButton({
    super.key,
    required this.state,
    required this.busy,
    required this.onConnect,
    required this.onDisconnect,
  });

  bool get _isConnectedOrConnecting =>
      state == VpnSessionState.connected ||
      state == VpnSessionState.connecting ||
      state == VpnSessionState.reconnecting;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 160,
      height: 160,
      child: FilledButton(
        onPressed: busy ? null : (_isConnectedOrConnecting ? onDisconnect : onConnect),
        style: FilledButton.styleFrom(shape: const CircleBorder()),
        child: busy
            ? const SizedBox(
                width: 32,
                height: 32,
                child: CircularProgressIndicator(strokeWidth: 3),
              )
            : Icon(
                _isConnectedOrConnecting ? Icons.power_settings_new : Icons.power_settings_new_outlined,
                size: 56,
              ),
      ),
    );
  }
}
