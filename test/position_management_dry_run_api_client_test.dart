import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

void main() {
  test('fetch latest position management dry-run uses read-only GET', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_runJson()), 200);
      }),
    );

    final result = await client.fetchPositionManagementDryRunLatest(
      provider: 'kis',
      market: 'KR',
    );

    expect(result.runId, 42);
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/strategy/positions/management/dry-run/latest');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters, isNot(contains('confirm_live')));
    expect(request.url.path, isNot(contains('/guarded-sell')));
    expect(request.url.path, isNot(contains('/submit')));
  });

  test('run once calls only position management dry-run endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_runJson()), 200);
      }),
    );

    await client.runPositionManagementDryRunOnce(symbol: '005930');

    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.path, '/strategy/positions/management/run-dry-run-once');
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body['provider'], 'kis');
    expect(body['market'], 'KR');
    expect(body['symbol'], '005930');
    expect(body['include_sell_preflight'], isTrue);
    expect(body, isNot(contains('confirm_live')));
    expect(body, isNot(contains('guarded_sell')));
    expect(request.url.path, isNot(contains('/guarded-sell')));
    expect(request.url.path, isNot(contains('/manual')));
  });
}

Map<String, dynamic> _runJson() {
  return {
    'run_id': 42,
    'generated_at': '2026-07-07T09:00:00Z',
    'provider': 'kis',
    'market': 'KR',
    'trigger_source': 'manual_position_management_dry_run',
    'dry_run_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'positions_checked': 1,
    'exit_candidate_count': 0,
    'critical_candidate_count': 0,
    'warning_candidate_count': 0,
    'simulated_sell_preflight_count': 0,
    'blocked_preflight_count': 0,
    'sync_required_count': 0,
    'duplicate_sell_conflict_count': 0,
    'result_status': 'completed',
    'primary_reason': 'no_exit_candidates',
    'risk_flags': const ['dry_run_only'],
    'gating_notes': const ['No order path was called.'],
    'candidates': const [],
    'sell_preflight_results': const [],
    'next_safe_actions': const ['Continue monitoring.'],
    'priority': 'positions_first',
    'entry_orders_allowed': false,
    'exit_orders_allowed': false,
    'dry_run_monitoring_only': true,
    'scheduler_enabled': false,
    'scheduler_dry_run_only': true,
    'scheduler_allow_live_orders': false,
    'safety': const {'dry_run_only': true},
  };
}
