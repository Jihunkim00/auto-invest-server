import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'automation_release_model_test.dart';

void main() {
  test('status uses release status endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationReleaseStatusJson()), 200);
      }),
    );

    final status = await api.fetchAutomationReleaseStatus();

    expect(status.releaseEnabled, isTrue);
    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/automation/release/status');
  });

  test('preflight posts empty body to release preflight endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationReleaseStatusJson()), 200);
      }),
    );

    await api.runAutomationReleasePreflight();

    expect(requests.single.method, 'POST');
    expect(requests.single.url.path, '/automation/release/preflight');
    expect(jsonDecode(requests.single.body), const <String, dynamic>{});
  });

  test('arm posts release acknowledgement only', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationReleaseStatusJson()), 200);
      }),
    );

    await api.armAutomationRelease(
      operatorAcknowledgedRisks: true,
      reason: 'operator reviewed',
      language: 'en',
      locale: 'en-US',
    );

    final body = jsonDecode(requests.single.body) as Map<String, dynamic>;
    expect(requests.single.url.path, '/automation/release/arm');
    expect(body['operator_acknowledged_risks'], isTrue);
    expect(body['release_mode'], 'controlled_phase1');
    expect(body.containsKey('dry_run'), isFalse);
    expect(body.containsKey('kill_switch'), isFalse);
    expect(body.containsKey('kis_real_order_enabled'), isFalse);
  });

  test('disarm calls only release disarm endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode(automationReleaseStatusJson(releaseEnabled: false)),
          200,
        );
      }),
    );

    await api.disarmAutomationRelease(reason: 'pause');

    expect(requests.single.method, 'POST');
    expect(requests.single.url.path, '/automation/release/disarm');
    expect(jsonDecode(requests.single.body), containsPair('reason', 'pause'));
  });

  test('monitoring cycle body has no live override fields', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(automationReleaseCycleJson()), 200);
      }),
    );

    await api.runAutomationReleaseCycleOnce(
      mode: 'monitoring',
      language: 'en',
      locale: 'en-US',
    );

    final body = jsonDecode(requests.single.body) as Map<String, dynamic>;
    expect(requests.single.url.path, '/automation/release/run-cycle-once');
    expect(body['mode'], 'monitoring');
    expect(body['operator_acknowledged_risks'], isFalse);
    for (final forbidden in [
      'confirm_live',
      'force_run',
      'skip_gates',
      'dry_run',
      'kis_real_order_enabled',
    ]) {
      expect(body.containsKey(forbidden), isFalse);
    }
  });
}
