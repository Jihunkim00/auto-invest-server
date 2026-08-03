import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

void main() {
  test('fetchOperationMode decodes Korean JSON response from bodyBytes',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return _utf8Response({
          'requested_mode': 'live',
          'effective_mode': 'live',
          'display_label': '실전 모드',
          'status': 'active',
          'safety_status': 'ready',
          'can_change_mode': true,
          'can_enter_paper': true,
          'can_enter_live': true,
          'can_enter_paused': true,
          'requires_acknowledgement': {'live': true},
          'mode_drift_detected': false,
          'blocking_reasons': const [],
          'warnings': [
            {'code': 'market', 'message': '한국 장 시작 전입니다.'},
          ],
          'underlying_state': const {},
        });
      }),
    );

    final status = await api.fetchOperationMode();

    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/app/operation-mode');
    expect(status.displayLabel, '실전 모드');
    expect(status.warnings.single.message, '한국 장 시작 전입니다.');
    _expectNoMojibake(status.displayLabel);
    _expectNoMojibake(status.warnings.single.message);
  });

  test('updateOperationMode preserves Korean error response text', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        expect(request.method, 'PUT');
        expect(request.url.path, '/app/operation-mode');
        expect(jsonDecode(request.body), {
          'mode': 'live',
          'acknowledged': true,
          'reason': 'settings_ui',
        });
        return _utf8Response(
          {
            'message': '실전 모드 전환이 차단되었습니다.',
            'blocking_reasons': [
              {'code': 'dry_run', 'message': 'dry_run 해제가 필요합니다.'},
            ],
          },
          statusCode: 409,
        );
      }),
    );

    await expectLater(
      api.updateOperationMode(
        mode: 'live',
        acknowledged: true,
        reason: 'settings_ui',
      ),
      throwsA(
        isA<ApiRequestException>()
            .having((e) => e.statusCode, 'statusCode', 409)
            .having(
              (e) => e.message,
              'message',
              allOf(
                contains('실전 모드 전환이 차단되었습니다.'),
                isNot(contains('ì')),
                isNot(contains(String.fromCharCode(0xFFFD))),
              ),
            ),
      ),
    );
    expect(requests, hasLength(1));
  });
}

http.Response _utf8Response(
  Map<String, dynamic> body, {
  int statusCode = 200,
}) {
  return http.Response.bytes(
    utf8.encode(jsonEncode(body)),
    statusCode,
    headers: const {'content-type': 'application/json; charset=utf-8'},
  );
}

void _expectNoMojibake(String value) {
  for (final marker in ['ì', 'ë', 'ê', String.fromCharCode(0xFFFD)]) {
    expect(value, isNot(contains(marker)));
  }
}
