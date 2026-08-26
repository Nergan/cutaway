import 'package:flutter/material.dart';

import '../../domain/entities/vpn_session_state.dart';

class StatusBadge extends StatelessWidget {
  final VpnSessionState state;
  const StatusBadge({super.key, required this.state});

  @override
  Widget build(BuildContext context) {
    final String label;
    final Color color;
    switch (state) {
      case VpnSessionState.disconnected:
        label = 'Disconnected';
        color = Colors.grey;
        break;
      case VpnSessionState.connecting:
        label = 'Connecting…';
        color = Colors.amber;
        break;
      case VpnSessionState.connected:
        label = 'Connected';
        color = Colors.greenAccent;
        break;
      case VpnSessionState.reconnecting:
        label = 'Reconnecting…';
        color = Colors.amber;
        break;
      case VpnSessionState.failed:
        label = 'Connection failed';
        color = Colors.redAccent;
        break;
    }

    return Chip(
      label: Text(label),
      backgroundColor: color.withOpacity(0.15),
      labelStyle: TextStyle(color: color),
      side: BorderSide(color: color.withOpacity(0.4)),
    );
  }
}
