import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/auto_exit_candidates_panel.dart';
import 'package:auto_invest_dashboard/models/auto_exit_candidate.dart';
import 'package:auto_invest_dashboard/models/position_exit_review.dart';

void main() {
  testWidgets('auto exit candidates panel renders Korean default labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeAutoExitApi())
      ..autoExitCandidates = AutoExitCandidates.fromJson(_candidatesJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.byKey(const ValueKey('auto-exit-candidates-panel')),
        findsOneWidget);
    expect(find.text(controller.strings.autoExitCandidates), findsOneWidget);
    expect(find.textContaining(controller.strings.positionMonitoring),
        findsOneWidget);
    expect(find.text(controller.strings.operatorReadOnly), findsOneWidget);
    expect(find.text(controller.strings.operatorNoLiveOrders), findsOneWidget);
    expect(find.text(controller.strings.noBrokerSubmitDisplay), findsOneWidget);
    expect(find.text(controller.strings.stopLossCandidate), findsWidgets);
    expect(find.text(controller.strings.takeProfitCandidate), findsWidgets);
    expect(find.text(controller.strings.syncRequired), findsWidgets);

    controller.dispose();
  });

  testWidgets('auto exit candidates panel renders English labels',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(
      _FakeAutoExitApi(),
      language: AppLanguage.english,
    )..autoExitCandidates = AutoExitCandidates.fromJson(_candidatesJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Auto Exit Candidates'), findsOneWidget);
    expect(find.textContaining('Position Monitoring'), findsOneWidget);
    expect(find.text('Read Only'), findsOneWidget);
    expect(find.text('No Live Orders'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    expect(find.text('Stop-Loss Candidate'), findsWidgets);
    expect(find.text('Take-Profit Candidate'), findsWidgets);
    expect(find.text('Sync Required'), findsWidgets);

    controller.dispose();
  });

  testWidgets('sync-required candidate disables sell preflight button',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutoExitApi();
    final controller = _controller(api, language: AppLanguage.english)
      ..autoExitCandidates = AutoExitCandidates.fromJson(
        _candidatesJson(candidates: [_candidate('sync_required')]),
      );

    await tester.pumpWidget(_wrap(controller));

    final button = tester.widget<FilledButton>(
      find.byKey(const ValueKey('auto-exit-candidate-sell-preflight-005930')),
    );
    expect(button.onPressed, isNull);
    expect(find.text('Sync Required'), findsWidgets);
    expect(api.preflightCalls, 0);

    controller.dispose();
  });

  testWidgets('run sell preflight calls only preflight endpoint',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeAutoExitApi();
    final controller = _controller(api, language: AppLanguage.english)
      ..autoExitCandidates = AutoExitCandidates.fromJson(_candidatesJson());

    await tester.pumpWidget(_wrap(controller));

    final button =
        find.byKey(const ValueKey('auto-exit-candidate-sell-preflight-005930'));
    await tester.ensureVisible(button);
    await tester.pumpAndSettle();
    await tester.tap(button);
    await tester.pumpAndSettle();

    expect(api.preflightCalls, 1);
    expect(api.lastPreflightSymbol, '005930');
    expect(api.guardedSellCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(api.schedulerCalls, 0);

    controller.dispose();
  });

  testWidgets('auto exit candidates panel has no unsafe controls',
      (tester) async {
    await _setLargeView(tester);
    final controller =
        _controller(_FakeAutoExitApi(), language: AppLanguage.english)
          ..autoExitCandidates = AutoExitCandidates.fromJson(_candidatesJson());

    await tester.pumpWidget(_wrap(controller));

    for (final label in [
      'Sell Now',
      'Execute Sell',
      'Force Sell',
      'Auto Sell',
      'Liquidate All',
      'Retry Sell',
      'Enable Live Scheduler',
      'Auto Exit All',
    ]) {
      expect(find.text(label), findsNothing);
    }

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 6400);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(
  _FakeAutoExitApi api, {
  AppLanguage language = AppLanguage.korean,
}) {
  return DashboardController(
    api,
    autoload: false,
    initialLanguage: language,
  )
    ..selectedProvider = SelectedProvider.kis
    ..selectedPortfolioMarket = PortfolioMarket.kr;
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AutoExitCandidatesPanel(controller: controller),
      ),
    ),
  );
}

class _FakeAutoExitApi extends ApiClient {
  int refreshCalls = 0;
  int preflightCalls = 0;
  int guardedSellCalls = 0;
  int manualSubmitCalls = 0;
  int schedulerCalls = 0;
  String? lastPreflightSymbol;

  @override
  Future<AutoExitCandidates> fetchAutoExitCandidates({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    bool includeDetails = true,
    String? minSeverity,
  }) async {
    refreshCalls += 1;
    return AutoExitCandidates.fromJson(_candidatesJson());
  }

  @override
  Future<PositionSellPreflightResult> runPositionSellPreflight({
    required String symbol,
    String provider = 'kis',
    String market = 'KR',
    String quantityMode = 'full',
    double? quantity,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    preflightCalls += 1;
    lastPreflightSymbol = symbol;
    return PositionSellPreflightResult.fromJson(_preflightJson());
  }
}

Map<String, dynamic> _candidatesJson({List<Map<String, dynamic>>? candidates}) {
  final items = candidates ??
      [
        _candidate('stop_loss', severity: 'critical'),
        _candidate('take_profit', severity: 'warning', symbol: '000660'),
      ];
  return {
    'generated_at': '2026-07-07T09:00:00Z',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'summary': {
      'candidate_count': items.length,
      'critical_count':
          items.where((item) => item['severity'] == 'critical').length,
      'warning_count':
          items.where((item) => item['severity'] == 'warning').length,
      'info_count': items.where((item) => item['severity'] == 'info').length,
      'stop_loss_count':
          items.where((item) => item['candidate_type'] == 'stop_loss').length,
      'take_profit_count':
          items.where((item) => item['candidate_type'] == 'take_profit').length,
      'trend_breakdown_count': 0,
      'manual_review_count': items
          .where((item) => item['candidate_type'] == 'manual_review')
          .length,
      'duplicate_sell_block_count': items
          .where((item) => item['candidate_type'] == 'duplicate_sell_conflict')
          .length,
      'sync_required_count': items
          .where((item) => item['candidate_type'] == 'sync_required')
          .length,
    },
    'safety_flags': const ['read_only', 'no_live_orders', 'no_broker_submit'],
    'candidates': items,
    'details': const {'position_count': 2},
  };
}

Map<String, dynamic> _candidate(
  String type, {
  String severity = 'warning',
  String symbol = '005930',
}) {
  final blocked = type == 'sync_required' || type == 'duplicate_sell_conflict';
  return {
    'candidate_id': 'auto-exit:kis:KR:$symbol:$type:20260707',
    'symbol': symbol,
    'provider': 'kis',
    'market': 'KR',
    'candidate_type': type,
    'severity': severity,
    'status': 'active',
    'action_hint':
        type == 'sync_required' ? 'sync_required' : 'run_sell_preflight',
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
    'stop_loss_triggered': type == 'stop_loss',
    'take_profit_triggered': type == 'take_profit',
    'trend_breakdown_triggered': false,
    'momentum_note': null,
    'risk_flags': [type],
    'gating_notes': const ['Read-only candidate detection.'],
    'primary_reason': '$type reason',
    'next_safe_action': 'Run sell preflight for operator review.',
    'related_position_id': null,
    'related_buy_order_id': 7,
    'related_lifecycle_id': null,
    'open_sell_order_conflict': type == 'duplicate_sell_conflict',
    'sync_required': type == 'sync_required',
    'can_run_sell_preflight': !blocked,
    'sell_preflight_endpoint_hint':
        blocked ? null : '/strategy/positions/$symbol/sell-preflight',
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
