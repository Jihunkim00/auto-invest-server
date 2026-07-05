import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'daily_ops_summary_model_test.dart';

void main() {
  test('fetchDailyOpsSummary uses GET with safe query parameters', () async {
    final seenRequests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        seenRequests.add(request);
        return http.Response(jsonEncode(dailyOpsSummaryJson()), 200);
      }),
    );

    final summary = await client.fetchDailyOpsSummary(
      provider: 'kis',
      market: 'KR',
      date: '2026-07-03',
      includeDetails: false,
    );

    expect(summary.date, '2026-07-03');
    expect(seenRequests, hasLength(1));
    final request = seenRequests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/ops/daily-summary');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters['date'], '2026-07-03');
    expect(request.url.queryParameters['include_details'], 'false');
    expect(request.url.queryParameters.containsKey('_ts'), isTrue);
  });
}
