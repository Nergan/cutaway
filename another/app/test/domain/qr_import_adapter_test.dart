import 'package:flutter_test/flutter_test.dart';

import 'package:another/infrastructure/qr/qr_import_adapter.dart';

void main() {
  group('parseInviteDeepLink', () {
    test('parses a well-formed invite link', () {
      final payload = parseInviteDeepLink(
        'another://enroll?token=abc123&cp=https%3A%2F%2Fcf-worker.another.example',
      );

      expect(payload.enrollmentToken, 'abc123');
      expect(payload.controlPlaneUrl, 'https://cf-worker.another.example');
    });

    test('trims surrounding whitespace (common when pasted manually)', () {
      final payload = parseInviteDeepLink(
        '  another://enroll?token=abc123&cp=https%3A%2F%2Fcp.example  ',
      );
      expect(payload.enrollmentToken, 'abc123');
    });

    test('rejects a link with the wrong scheme', () {
      expect(
        () => parseInviteDeepLink('https://enroll?token=abc123&cp=https://cp.example'),
        throwsA(isA<InviteParseException>()),
      );
    });

    test('rejects a link missing the token', () {
      expect(
        () => parseInviteDeepLink('another://enroll?cp=https://cp.example'),
        throwsA(isA<InviteParseException>()),
      );
    });

    test('rejects a link missing the control-plane URL', () {
      expect(
        () => parseInviteDeepLink('another://enroll?token=abc123'),
        throwsA(isA<InviteParseException>()),
      );
    });

    test('rejects garbage input without throwing an unrelated exception type', () {
      expect(
        () => parseInviteDeepLink('not a url at all'),
        throwsA(isA<InviteParseException>()),
      );
    });
  });
}
