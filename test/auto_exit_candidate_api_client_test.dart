import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

void main() {
  test('fetch auto exit candidates calls read-only GET endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_candidatesJson()), 200);
      }),
    );

    final result = await client.fetchAutoExitCandidates(
      provider: 'kis',
      market: 'KR',
      symbol: '005930',
      includeDetails: true,
      minSeverity: 'warning',
    );

    expect(result.summary.candidateCount, 1);
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/strategy/positions/exit-candidates');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters['symbol'], '005930');
    expect(request.url.queryParameters['include_details'], 'true');
    expect(request.url.queryParameters['min_severity'], 'warning');
    expect(request.url.queryParameters, isNot(contains('confirm_live')));
    expect(request.url.path, isNot(contains('/guarded-sell')));
    expect(request.url.path, isNot(contains('/submit')));
    expect(request.url.path, isNot(contains('/sync')));
  });

  test('sell preflight request does not send live confirmation', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_preflightJson()), 200);
      }),
    );

    await client.runPositionSellPreflight(symbol: '005930');

    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.path, '/strategy/positions/005930/sell-preflight');
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body, isNot(contains('confirm_live')));
    expect(request.url.path, isNot(contains('/guarded-sell')));
  });
}

Map<String, dynamic> _candidatesJson() {
  return {
    'generated_at': '2026-07-07T09:00:00Z',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'summary': {
      'candidate_count': 1,
      'critical_count': 1,
      'warning_count': 0,
      'info_count': 0,
      'stop_loss_count': 1,
      'take_profit_count': 0,
      'trend_breakdown_count': 0,
      'manual_review_count': 0,
      'duplicate_sell_block_count': 0,
      'sync_required_count': 0,
    },
    'safety_flags': const ['read_only', 'no_live_orders'],
    'candidates': [
      {
        'candidate_id': 'auto-exit:kis:KR:005930:stop_loss:20260707',
        'symbol': '005930',
        'provider': 'kis',
        'market': 'KR',
        'candidate_type': 'stop_loss',
        'severity': 'critical',
        'status': 'active',
        'action_hint': 'run_sell_preflight',
        'position_quantity': 2,
        'available_quantity': 2,
        'average_price': 5000,
        'current_price': 4900,
        'cost_basis': 10000,
        'current_value': 9800,
        'unrealized_pl': -200,
        'unrealized_pl_pct': -0.02,
        'stop_loss_threshold_pct': 2,
        'take_profit_threshold_pct': 2,
        'stop_loss_triggered': true,
        'take_profit_triggered': false,
        'trend_breakdown_triggered': false,
        'risk_flags': const ['stop_loss_triggered'],
        'gating_notes': const ['Read-only candidate detection.'],
        'primary_reason': 'Stop-loss threshold was reached.',
        'next_safe_action': 'Run sell preflight.',
        'open_sell_order_conflict': false,
        'sync_required': false,
        'can_run_sell_preflight': true,
        'sell_preflight_endpoint_hint':
            '/strategy/positions/005930/sell-preflight',
      },
    ],
  };
}

Map<String, dynamic> _preflightJson() {
  return {
    'symbol': '005930',
    'provider': 'kis',
    'market': 'KR',
    'preflight_status': 'allowed',
    'can_submit_after_confirmation': true,
    'final_confirmation_required': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'position_exists': true,
    'quantity_held': 2,
    'available_quantity': 2,
    'requested_quantity': 2,
    'estimated_sell_notional': 9800,
    'current_price': 4900,
    'average_price': 5000,
    'cost_basis': 10000,
    'current_value': 9800,
    'unrealized_pl': -200,
    'unrealized_pl_pct': -0.02,
    'stop_loss_threshold_pct': 2,
    'take_profit_threshold_pct': 2,
    'stop_loss_triggered': true,
    'take_profit_triggered': false,
    'kill_switch': false,
    'dry_run': false,
    'kis_real_order_enabled': true,
    'market_session_allowed': true,
    'no_new_entry_window_allowed': true,
    'risk_flags': const ['stop_loss_triggered'],
    'gating_notes': const ['preflight_only'],
    'checklist': const [],
    'primary_block_reason': null,
    'next_required_action': 'final_operator_confirmation_required',
    'safety': const {'read_only': true},
  };
}
