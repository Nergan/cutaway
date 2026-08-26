import 'package:flutter/material.dart';

import '../../app_state.dart';

class SettingsScreen extends StatelessWidget {
  final AppState appState;
  const SettingsScreen({super.key, required this.appState});

  @override
  Widget build(BuildContext context) {
    final profile = appState.profile;

    return Scaffold(
      appBar: AppBar(title: const Text('Settings')),
      body: ListView(
        children: [
          if (profile != null) ...[
            ListTile(
              leading: const Icon(Icons.badge_outlined),
              title: const Text('Device ID'),
              subtitle: Text(profile.clientId),
            ),
            ListTile(
              leading: const Icon(Icons.link),
              title: const Text('Control plane'),
              subtitle: Text(profile.controlPlaneUrl),
            ),
            ListTile(
              leading: const Icon(Icons.event_available_outlined),
              title: const Text('Enrolled'),
              subtitle: Text(profile.enrolledAt.toLocal().toString()),
            ),
            const Divider(),
          ],
          ListTile(
            leading: const Icon(Icons.info_outline),
            title: const Text('About'),
            subtitle: const Text(
              'Another VPN — a private VPN for a trusted group, '
              'resistant to DPI detection. Not designed for Tor-level '
              'anonymity — see docs/architecture.md §1 in the project repo.',
            ),
          ),
        ],
      ),
    );
  }
}
