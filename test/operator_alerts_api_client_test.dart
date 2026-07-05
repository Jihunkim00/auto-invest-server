import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'operator_alerts_model_test.dart';

void main() {
  test('fetchOperatorAlerts uses GET with safe query parameters', () async {
    final seenRequests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        seenRequests.add(request);
        return http.Response(jsonEncode(operatorAlertsJson()), 200);
      }),
    );

    final alerts = await client.fetchOperatorAlerts(
      provider: 'kis',
      market: 'KR',
      severity: 'warning',
      status: 'active',
      limit: 25,
      includeDetails: false,
    );

    expect(alerts.provider, 'kis');
    expect(seenRequests, hasLength(1));
    final request = seenRequests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/ops/alerts');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters['severity'], 'warning');
    expect(request.url.queryParameters['status'], 'active');
    expect(request.url.queryParameters['limit'], '25');
    expect(request.url.queryParameters['include_details'], 'false');
    expect(request.url.queryParameters.containsKey('_ts'), isTrue);
  });
}
