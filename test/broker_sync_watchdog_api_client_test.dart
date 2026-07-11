import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'broker_sync_watchdog_model_test.dart';

void main() {
  test('status uses watchdog status endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(brokerSyncWatchdogJson()), 200);
      }),
    );

    final result = await api.fetchBrokerSyncWatchdogStatus();

    expect(result.healthy, isTrue);
    expect(requests, hasLength(1));
    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/broker-sync/watchdog/status');
    expect(requests.single.url.queryParameters['provider'], 'kis');
    expect(requests.single.url.queryParameters['market'], 'KR');
  });

  test('latest uses watchdog latest endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(brokerSyncWatchdogJson()), 200);
      }),
    );

    await api.fetchBrokerSyncWatchdogLatest(provider: 'kis', market: 'KR');

    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/broker-sync/watchdog/latest');
    expect(requests.single.url.queryParameters['provider'], 'kis');
    expect(requests.single.url.queryParameters['market'], 'KR');
  });

  test('run once posts only to watchdog run endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(brokerSyncWatchdogJson()), 200);
      }),
    );

    await api.runBrokerSyncWatchdogOnce();

    expect(requests.single.method, 'POST');
    expect(requests.single.url.path, '/broker-sync/watchdog/run-once');
    expect(requests.single.url.queryParameters['provider'], 'kis');
    expect(requests.single.url.queryParameters['market'], 'KR');
    expect(jsonDecode(requests.single.body), <String, dynamic>{});
  });
}
