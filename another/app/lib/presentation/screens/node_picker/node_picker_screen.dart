import 'package:flutter/material.dart';

import '../../../domain/entities/node_descriptor.dart';
import '../../app_state.dart';

class NodePickerScreen extends StatelessWidget {
  final AppState appState;
  const NodePickerScreen({super.key, required this.appState});

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: appState,
      builder: (context, _) {
        final nodes = appState.profile?.nodes ?? const <NodeDescriptor>[];
        final activeName = appState.snapshot.activeNodeName;

        return Scaffold(
          appBar: AppBar(title: const Text('Nodes')),
          body: nodes.isEmpty
              ? const Center(child: Text('No nodes available yet.'))
              : ListView.builder(
                  itemCount: nodes.length,
                  itemBuilder: (context, index) {
                    final node = nodes[index];
                    final isActive = node.name == activeName;
                    return ListTile(
                      leading: Icon(
                        node.tier == 'tier2-target' ? Icons.dns : Icons.cloud_outlined,
                      ),
                      title: Text(node.name),
                      subtitle: Text('${node.transport} · ${node.tier}'),
                      trailing: isActive
                          ? const Icon(Icons.check_circle, color: Colors.greenAccent)
                          : (appState.isBusy ? null : const Icon(Icons.chevron_right)),
                      enabled: !appState.isBusy && !isActive,
                      onTap: isActive ? null : () => appState.switchToNode(node),
                    );
                  },
                ),
        );
      },
    );
  }
}
