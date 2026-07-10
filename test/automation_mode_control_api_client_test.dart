import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'automation_mode_control_model_test.dart';

void main() {
  test('status uses the read-only automation mode endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationModeStatusJson()), 200);
      }),
    );

    final status = await api.fetchAutomationModeStatus();

    expect(status.automationMode, 'off');
    expect(requests, hasLength(1));
    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/automation/mode/status');
  });

  test('set mode sends only the control-center payload', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode(
            automationModeStatusJson(
              mode: 'phase1_live_ready',
              label: 'Phase 1 Live Ready',
              effectiveStatus: 'live_ready_blocked',
              blockingReasons: const ['dry_run_enabled'],
              warningReasons: const ['dry_run_is_separate'],
            ),
          ),
          200,
        );
      }),
    );

    final status = await api.setAutomationMode(
      automationMode: 'phase1_live_ready',
      reason: 'operator review',
      operatorAcknowledgedRisks: true,
      language: 'en',
      locale: 'en-US',
    );

    expect(status.automationMode, 'phase1_live_ready');
    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.path, '/automation/mode/set');
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body, {
      'automation_mode': 'phase1_live_ready',
      'reason': 'operator review',
      'operator_acknowledged_risks': true,
      'language': 'en',
      'locale': 'en-US',
    });
    expect(body.keys, isNot(contains('dry_run')));
    expect(body.keys, isNot(contains('kill_switch')));
    expect(body.keys, isNot(contains('kis_real_order_enabled')));
    expect(body.keys, isNot(contains('confirm_live')));
    expect(body.keys, isNot(contains('force_run')));
    expect(body.keys, isNot(contains('skip_gates')));
  });

  test('turn off uses the dedicated off endpoint without safety-gate payload',
      () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationModeStatusJson()), 200);
      }),
    );

    final status = await api.turnOffAutomationMode(
      reason: 'operator stop',
      language: 'ko',
      locale: 'ko-KR',
    );

    expect(status.automationMode, 'off');
    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.path, '/automation/mode/off');
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body, {
      'reason': 'operator stop',
      'language': 'ko',
      'locale': 'ko-KR',
    });
    expect(body.keys, isNot(contains('dry_run')));
    expect(body.keys, isNot(contains('kill_switch')));
    expect(body.keys, isNot(contains('kis_real_order_enabled')));
  });
}
