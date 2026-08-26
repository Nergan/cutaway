import 'package:flutter/material.dart';

import '../../../domain/entities/vpn_session_state.dart';
import '../../app_state.dart';
import '../../widgets/connect_button.dart';
import '../../widgets/status_badge.dart';
import '../node_picker/node_picker_screen.dart';
import '../settings/settings_screen.dart';

class HomeScreen extends StatelessWidget {
  final AppState appState;
  const HomeScreen({super.key, required this.appState});

  String _formatBytes(int bytes) {
    const units = ['B', 'KB', 'MB', 'GB'];
    double value = bytes.toDouble();
    var unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
      value /= 1024;
      unitIndex++;
    }
    return '${value.toStringAsFixed(1)} ${units[unitIndex]}';
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = appState.snapshot;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Another'),
        actions: [
          IconButton(
            icon: const Icon(Icons.dns_outlined),
            tooltip: 'Nodes',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => NodePickerScreen(appState: appState)),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.settings_outlined),
            tooltip: 'Settings',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => SettingsScreen(appState: appState)),
            ),
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: appState.refreshStatus,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: [
            const SizedBox(height: 32),
            Center(child: StatusBadge(state: snapshot.state)),
            const SizedBox(height: 32),
            Center(
              child: ConnectButton(
                state: snapshot.state,
                busy: appState.isBusy,
                onConnect: appState.connect,
                onDisconnect: appState.disconnect,
              ),
            ),
            const SizedBox(height: 24),
            if (snapshot.activeNodeName != null)
              Center(child: Text('Connected via ${snapshot.activeNodeName}')),
            if (snapshot.state == VpnSessionState.connected)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Center(
                  child: Text(
                    '${_formatBytes(snapshot.bytesSent)} sent · ${_formatBytes(snapshot.bytesRecv)} received',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
              ),
            if (appState.lastError != null)
              Padding(
                padding: const EdgeInsets.only(top: 24),
                child: Center(
                  child: Text(
                    appState.lastError!,
                    style: const TextStyle(color: Colors.redAccent),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
