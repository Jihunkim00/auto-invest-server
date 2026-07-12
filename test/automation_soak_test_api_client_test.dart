import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'automation_soak_test_model_test.dart';

void main() {
  test('status uses automation soak status endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationSoakStatusJson()), 200);
      }),
    );

    final status = await api.fetchAutomationSoakStatus();

    expect(status.soakEnabled, isTrue);
    expect(requests, hasLength(1));
    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/automation/soak/status');
  });

  test('run once posts only dry-run soak request body', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationSoakRunJson()), 200);
      }),
    );

    await api.runAutomationSoakOnce(language: 'en', locale: 'en-US');

    expect(requests.single.method, 'POST');
    expect(requests.single.url.path, '/automation/soak/run-once');
    final body = jsonDecode(requests.single.body) as Map<String, dynamic>;
    expect(body, {
      'provider': 'kis',
      'market': 'KR',
      'mode': 'dry_run_monitoring',
      'trigger_source': 'manual_soak_test',
      'language': 'en',
      'locale': 'en-US',
      'operator_acknowledged_risks': false,
    });
    expect(body.containsKey('confirm_live'), isFalse);
    expect(body.containsKey('dry_run'), isFalse);
  });

  test('reset kill latch posts acknowledgement and reason only', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationSoakStatusJson()), 200);
      }),
    );

    await api.resetAutomationSoakKillLatch(
      operatorAcknowledgedRisks: true,
      reason: 'reviewed',
    );

    expect(requests.single.method, 'POST');
    expect(requests.single.url.path, '/automation/soak/reset-kill-latch');
    expect(jsonDecode(requests.single.body), {
      'operator_acknowledged_risks': true,
      'reason': 'reviewed',
    });
  });
}
