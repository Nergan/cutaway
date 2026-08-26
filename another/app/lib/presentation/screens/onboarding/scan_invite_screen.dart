import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../infrastructure/qr/qr_import_adapter.dart';
import '../../app_state.dart';

/// ScanInviteScreen — показывается, когда локальный профиль ещё не найден
/// (§7.1 спецификации: онбординг устройства). Поддерживает и сканирование
/// QR-кода камерой, и ручной ввод инвайт-ссылки — второе особенно полезно
/// на десктопе, где камера обычно недоступна/неудобна.
class ScanInviteScreen extends StatefulWidget {
  final AppState appState;
  const ScanInviteScreen({super.key, required this.appState});

  @override
  State<ScanInviteScreen> createState() => _ScanInviteScreenState();
}

class _ScanInviteScreenState extends State<ScanInviteScreen> {
  final _manualController = TextEditingController();
  bool _showManualEntry = false;
  String? _localError;
  bool _handledOnce = false;

  @override
  void dispose() {
    _manualController.dispose();
    super.dispose();
  }

  Future<void> _handleInviteLink(String raw) async {
    if (_handledOnce) return; // не дёргаем enroll() повторно на каждый кадр камеры
    InvitePayload payload;
    try {
      payload = parseInviteDeepLink(raw);
    } on InviteParseException catch (e) {
      setState(() => _localError = e.message);
      return;
    }

    _handledOnce = true;
    setState(() => _localError = null);

    try {
      await widget.appState.enroll(
        controlPlaneUrl: payload.controlPlaneUrl,
        enrollmentToken: payload.enrollmentToken,
      );
    } finally {
      // Если попытка не удалась, разрешаем повторное сканирование/ввод.
      if (widget.appState.profile == null) {
        _handledOnce = false;
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final appState = widget.appState;
    final error = _localError ?? appState.lastError;

    return Scaffold(
      appBar: AppBar(title: const Text('Add this device')),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: appState.isBusy
              ? const Center(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      CircularProgressIndicator(),
                      SizedBox(height: 16),
                      Text('Enrolling…'),
                    ],
                  ),
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const Text(
                      'Scan the invite QR code you received from the person '
                      'who administers this Another VPN, or paste the invite '
                      'link manually.',
                    ),
                    const SizedBox(height: 16),
                    if (!_showManualEntry)
                      Expanded(
                        child: ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: MobileScanner(
                            onDetect: (capture) {
                              final barcodes = capture.barcodes;
                              if (barcodes.isNotEmpty && barcodes.first.rawValue != null) {
                                _handleInviteLink(barcodes.first.rawValue!);
                              }
                            },
                          ),
                        ),
                      ),
                    if (_showManualEntry) ...[
                      TextField(
                        controller: _manualController,
                        decoration: const InputDecoration(
                          labelText: 'Invite link',
                          hintText: 'another://enroll?token=...&cp=...',
                          border: OutlineInputBorder(),
                        ),
                      ),
                      const SizedBox(height: 8),
                      FilledButton(
                        onPressed: () => _handleInviteLink(_manualController.text),
                        child: const Text('Continue'),
                      ),
                    ],
                    const SizedBox(height: 8),
                    TextButton(
                      onPressed: () => setState(() => _showManualEntry = !_showManualEntry),
                      child: Text(_showManualEntry ? 'Use camera instead' : 'Enter link manually instead'),
                    ),
                    if (error != null)
                      Padding(
                        padding: const EdgeInsets.only(top: 8),
                        child: Text(error, style: const TextStyle(color: Colors.redAccent)),
                      ),
                  ],
                ),
        ),
      ),
    );
  }
}
