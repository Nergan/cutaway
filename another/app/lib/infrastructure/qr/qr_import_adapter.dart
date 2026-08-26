/// InvitePayload — результат разбора QR-кода/ссылки-приглашения,
/// сгенерированной control-plane-admin (см.
/// control-plane-admin/another_admin/domain/device_provisioning_service.py:
/// `another://enroll?token=...&cp=...`).
class InvitePayload {
  final String enrollmentToken;
  final String controlPlaneUrl;

  const InvitePayload({
    required this.enrollmentToken,
    required this.controlPlaneUrl,
  });
}

class InviteParseException implements Exception {
  final String message;
  const InviteParseException(this.message);

  @override
  String toString() => 'InviteParseException: $message';
}

/// parseInviteDeepLink — не оформлен как порт/адаптер (нет внешнего
/// состояния) — чистая функция-утилита, как и generate_qr_png на стороне
/// control-plane-admin (см. adapters/qr_generator.py там же, тот же
/// принцип: "не всё нужно превращать в порт").
InvitePayload parseInviteDeepLink(String raw) {
  final uri = Uri.tryParse(raw.trim());
  if (uri == null || uri.scheme != 'another' || uri.host != 'enroll') {
    throw const InviteParseException('Not a valid Another invite link');
  }

  final token = uri.queryParameters['token'];
  final controlPlaneUrl = uri.queryParameters['cp'];

  if (token == null || token.isEmpty) {
    throw const InviteParseException('Invite link is missing the enrollment token');
  }
  if (controlPlaneUrl == null || controlPlaneUrl.isEmpty) {
    throw const InviteParseException('Invite link is missing the control-plane URL');
  }

  return InvitePayload(enrollmentToken: token, controlPlaneUrl: controlPlaneUrl);
}
