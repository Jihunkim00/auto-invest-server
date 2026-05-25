import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/ops_production_readiness.dart';

void main() {
  test('operations readiness API calls read-only endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_readinessJson()), 200);
      }),
    );

    final result = await client.fetchOpsProductionReadiness();

    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/ops/production-readiness');
    expect(requests.single.url.queryParameters['include_raw'], 'false');
    expect(requests.single.url.queryParameters['days'], '7');
    expect(requests.single.url.queryParameters['include_recent'], 'true');
    expect(requests.single.url.path, isNot(contains('/kis/orders')));
    expect(result.readinessOnly, isTrue);
    expect(result.overallStatus, 'BLOCKED');
  });

  testWidgets('operations readiness card renders default safe blocked state',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeOpsReadinessApi();
    final controller = _controller(api)
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('ops_production_readiness_card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(of: card, matching: find.text('Operations Readiness')),
      findsOneWidget,
    );
    for (final label in [
      'OPERATIONS READINESS',
      'SAFETY CHECK',
      'READINESS ONLY',
      'NO BROKER SUBMIT',
      'PRODUCTION CHECKLIST',
      'LIVE ORDER STATUS',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }
    expect(find.descendant(of: card, matching: find.text('BLOCKED')),
        findsWidgets);
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('scheduler_real_orders_disabled'),
      ),
      findsWidgets,
    );

    final refreshButton = find.descendant(
      of: card,
      matching: find.text('Refresh Operations Readiness'),
    );
    await tester.ensureVisible(refreshButton);
    await tester.tap(refreshButton);
    await tester.pumpAndSettle();

    expect(api.refreshCalls, 1);
    controller.dispose();
  });

  testWidgets('operations readiness safety checks render all status badges',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeOpsReadinessApi())
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('ops_production_readiness_card'));
    for (final status in ['PASS', 'WARN', 'FAIL', 'INFO']) {
      expect(
          find.descendant(of: card, matching: find.text(status)), findsWidgets);
    }
    expect(find.descendant(of: card, matching: find.text('Dry-run mode')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Stale orders')),
        findsOneWidget);
    expect(find.textContaining('Sync or resolve stale orders'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('operations readiness today activity renders counts',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeOpsReadinessApi())
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('ops_production_readiness_card'));
    expect(find.descendant(of: card, matching: find.text('Today Activity')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('3')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('0')), findsWidgets);
    expect(
      find.descendant(
        of: card,
        matching: find.text('scheduler_real_orders_disabled'),
      ),
      findsWidgets,
    );

    controller.dispose();
  });

  testWidgets('operations readiness renders issues and recommended actions',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeOpsReadinessApi())
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('ops_production_readiness_card'));
    expect(find.descendant(of: card, matching: find.text('Blocking Issues')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('Recommended Actions')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('kis_real_order_disabled'),
      ),
      findsWidgets,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.text('Keep dry_run=true for verification.'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('operations readiness raw payload is collapsed by default',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeOpsReadinessApi())
      ..latestOpsProductionReadiness =
          OpsProductionReadiness.fromJson(_readinessJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('ops_production_readiness_card'));
    expect(
      find.descendant(of: card, matching: find.text('Developer Raw Payload')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('"mode": "ops_production_readiness"'),
      ),
      findsNothing,
    );

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 9800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(_FakeOpsReadinessApi api) {
  return DashboardController(api, autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..krWatchlist = MarketWatchlist.empty('KR');
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => TestLabSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeOpsReadinessApi extends ApiClient {
  _FakeOpsReadinessApi()
      : result = OpsProductionReadiness.fromJson(_readinessJson());

  OpsProductionReadiness result;
  int refreshCalls = 0;

  @override
  Future<OpsProductionReadiness> fetchOpsProductionReadiness({
    bool includeRaw = false,
    int days = 7,
    bool includeRecent = true,
  }) async {
    refreshCalls += 1;
    return result;
  }
}

Map<String, dynamic> _readinessJson() {
  return {
    'mode': 'ops_production_readiness',
    'readiness_only': true,
    'production_ready': false,
    'live_trading_ready': false,
    'paper_or_dry_run_ready': true,
    'summary': {
      'overall_status': 'BLOCKED',
      'production_ready': false,
      'live_trading_ready': false,
      'paper_or_dry_run_ready': true,
      'dry_run': true,
      'kill_switch': false,
      'kis_enabled': false,
      'kis_real_order_enabled': false,
      'scheduler_enabled': false,
      'kis_scheduler_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'kis_scheduler_sell_enabled': false,
      'kis_scheduler_buy_enabled': false,
      'kis_live_auto_sell_enabled': false,
      'kis_live_auto_buy_enabled': false,
      'kis_limited_auto_sell_enabled': false,
      'kis_limited_auto_buy_enabled': false,
      'critical_issue_count': 1,
      'warning_count': 2,
    },
    'runtime': {'dry_run': true, 'kill_switch': false},
    'kis': {
      'kis_enabled': false,
      'kis_real_order_enabled': false,
      'real_order_possible': false,
    },
    'scheduler': {
      'scheduler_real_orders_allowed': false,
      'scheduler_sell_enabled': false,
      'scheduler_buy_enabled': false,
      'sell_review_before_buy': true,
    },
    'risk': {
      'today_broker_submit_count': 0,
      'unresolved_stale_orders': [
        {'order_id': 7, 'symbol': '005930'}
      ],
    },
    'today': {
      'date': '2026-05-25',
      'total_runs': 3,
      'blocked_count': 2,
      'failed_count': 1,
      'order_logs_created': 0,
      'broker_submits': 0,
      'top_block_reasons': [
        {'reason': 'scheduler_real_orders_disabled', 'count': 2}
      ],
    },
    'recent_activity': [
      {
        'type': 'trade_run',
        'mode': 'kis_scheduler_dry_run_orchestration',
        'trigger_source': 'scheduler_dry_run',
      },
      {
        'type': 'trade_run',
        'mode': 'kis_scheduler_guarded_sell',
        'trigger_source': 'scheduler_guarded_sell',
      },
    ],
    'safety_checks': [
      {
        'key': 'dry_run',
        'label': 'Dry-run mode',
        'status': 'PASS',
        'value': true,
        'message': 'Dry-run is enabled; real orders are blocked.',
        'recommended_action':
            'Keep dry-run enabled until final live checks pass.',
      },
      {
        'key': 'live_auto_buy_enabled',
        'label': 'Live auto buy',
        'status': 'WARN',
        'value': false,
        'message': 'Live auto buy is disabled.',
        'recommended_action': 'Keep scheduler buy disabled initially.',
      },
      {
        'key': 'stale_orders',
        'label': 'Stale orders',
        'status': 'FAIL',
        'value': [
          {'order_id': 7}
        ],
        'message': 'Unresolved stale orders exist.',
        'recommended_action':
            'Sync or resolve stale orders before enabling live automation.',
      },
      {
        'key': 'kis_enabled',
        'label': 'KIS enabled',
        'status': 'INFO',
        'value': false,
        'message': 'KIS integration is disabled.',
        'recommended_action': 'Enable KIS only after dry-run checks pass.',
      },
      {
        'key': 'kr_watchlist_baseline',
        'label': 'KR watchlist baseline',
        'status': 'PASS',
        'value': {'symbol_count': 50},
        'message': 'KR watchlist baseline is valid.',
        'recommended_action': 'Keep the KR baseline under review.',
      },
      {
        'key': 'db_writable',
        'label': 'DB writable',
        'status': 'PASS',
        'value': true,
        'message': 'Database writable check passed.',
        'recommended_action': 'Keep DATABASE_URL writable.',
      },
      {
        'key': 'production_docs_present',
        'label': 'Production docs',
        'status': 'PASS',
        'value': true,
        'message': 'Production documentation is present.',
        'recommended_action': 'Review docs before live trading.',
      },
      {
        'key': 'env_example_present',
        'label': '.env.example',
        'status': 'PASS',
        'value': true,
        'message': '.env.example is present.',
        'recommended_action': 'Keep safe defaults in .env.example.',
      },
    ],
    'blocking_issues': [
      'scheduler_real_orders_disabled',
      'kis_real_order_disabled',
    ],
    'warnings': ['missing_mdd_calculation'],
    'recommended_actions': [
      'Keep dry_run=true for verification.',
      'Run scheduler dry-run orchestration once.',
    ],
    'documentation': {
      'docs_present': true,
      'env_example_present': true,
    },
    'diagnostics': {'read_only': true},
  };
}
