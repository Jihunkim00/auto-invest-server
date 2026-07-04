import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'position_lifecycle_model_test.dart';

void main() {
  test('position lifecycle API uses read-only GET endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(positionLifecycleJson()), 200);
      }),
    );

    final lifecycle = await client.fetchPositionLifecycle(
      symbol: '005930',
      provider: 'kis',
      market: 'KR',
      status: 'all',
      limit: 25,
      includeEvents: true,
    );

    expect(lifecycle.items, hasLength(2));
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/strategy/positions/lifecycle');
    expect(request.url.queryParameters['symbol'], '005930');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters['status'], 'all');
    expect(request.url.queryParameters['limit'], '25');
    expect(request.url.queryParameters['include_events'], 'true');
    expect(request.url.queryParameters.containsKey('confirm_live'), isFalse);
    expect(request.url.queryParameters.containsKey('manual_submit'), isFalse);
    expect(request.url.queryParameters.containsKey('sync'), isFalse);
    expect(request.body, isEmpty);
  });
}
