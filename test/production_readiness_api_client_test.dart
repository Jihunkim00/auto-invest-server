import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

void main() {
  test('fetch production readiness calls read-only GET endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_readinessJson()), 200);
      }),
    );

    final result = await client.fetchOpsProductionReadiness(
      provider: 'kis',
      market: 'KR',
      includeDetails: true,
    );

    expect(result.overallStatus, 'blocked');
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/ops/production-readiness');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters['include_details'], 'true');
    expect(request.url.queryParameters, isNot(contains('confirm_live')));
    expect(request.url.path, isNot(contains('/submit')));
    expect(request.url.path, isNot(contains('/sync')));
    expect(request.url.path, isNot(contains('/settings')));
  });
}

Map<String, dynamic> _readinessJson() {
  return {
    'generated_at': '2026-07-06T09:00:00+09:00',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'overall_status': 'blocked',
    'readiness_score': 50,
    'summary': {
      'ready_count': 1,
      'warning_count': 1,
      'blocked_count': 1,
      'unknown_count': 0,
      'critical_block_count': 1,
      'can_use_guarded_live_buy': false,
      'can_use_guarded_live_sell': false,
      'can_enable_scheduler_live_orders': false,
      'scheduler_real_orders_allowed': false,
      'automation_unlock_allowed': false,
    },
    'checklist': const [],
    'blocking_reasons': const ['kis_real_order_enabled_for_live'],
    'warnings': const [],
    'next_safe_actions': const ['Review only.'],
    'safety_flags': const {'read_only': true},
  };
}
