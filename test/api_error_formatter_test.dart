import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_error_formatter.dart';

void main() {
  group('ApiErrorFormatter', () {
    test('formats safety gate HTTP 409 error', () {
      const errorJson = '{"internal_status":"REJECTED_BY_SAFETY_GATE","block_reasons":["market_closed","today_is_holiday"],"safety_checks":{},"real_order_submitted":false,"closure_name":"Christmas"}';
      const errorMessage = 'HTTP 409: $errorJson';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, 'No real order was submitted. Market is closed. Today is a holiday: Christmas.');
      expect(formatted, isNot(contains('safety_checks')));
      expect(formatted, isNot(contains('{')));
      expect(formatted, isNot(contains('}')));
    });

    test('formats safety gate with all block reasons', () {
      const errorJson = '{"internal_status":"REJECTED_BY_SAFETY_GATE","block_reasons":["market_closed","today_is_holiday","buy_entry_not_allowed_now","sell_entry_not_allowed_now","recent_dry_run_validation_missing","kill_switch_enabled","kis_disabled","kis_real_order_disabled","confirmation_required","dry_run_must_be_false"],"real_order_submitted":false}';
      const errorMessage = 'HTTP 409: $errorJson';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, contains('No real order was submitted.'));
      expect(formatted, contains('Market is closed.'));
      expect(formatted, contains('Today is a holiday.'));
      expect(formatted, contains('Buy entry is not allowed now.'));
      expect(formatted, contains('Sell entry is not allowed now.'));
      expect(formatted, contains('Dry-run validation is missing.'));
      expect(formatted, contains('Kill switch is enabled.'));
      expect(formatted, contains('KIS trading is disabled.'));
      expect(formatted, contains('KIS real-order submission is disabled.'));
      expect(formatted, contains('Live confirmation is required.'));
      expect(formatted, contains('Live submit requires dry_run=false.'));
    });

    test('formats KIS balance inquiry HTTP 502 error', () {
      const errorJson = '{"path":"/kis/inquire-balance","tr_id":"FHKST01010100","detail":{"message":"Balance inquiry failed","details":"Additional details"},"msg_cd":"EGW00123","msg1":"System error"}';
      const errorMessage = 'HTTP 502: $errorJson';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, 'KIS account check failed. Balance inquiry failed. TR ID: FHKST01010100. Code: EGW00123 System error Additional details');
    });

    test('formats generic KIS read-only HTTP 502 error', () {
      const errorJson = '{"path":"/kis/some-other-endpoint","detail":{"message":"Some error occurred"}}';
      const errorMessage = 'HTTP 502: $errorJson';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, 'KIS read-only error. Some error occurred');
    });

    test('falls back to original message for non-JSON errors', () {
      const errorMessage = 'Some other error';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, 'Some other error');
    });

    test('falls back to original message for non-matching status codes', () {
      const errorJson = '{"some": "json"}';
      const errorMessage = 'HTTP 500: $errorJson';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, 'HTTP 500: {"some": "json"}');
    });

    test('handles invalid JSON gracefully', () {
      const errorMessage = 'HTTP 409: invalid json';

      final formatted = ApiErrorFormatter.format(errorMessage);

      expect(formatted, 'HTTP 409: invalid json');
    });
  });
}