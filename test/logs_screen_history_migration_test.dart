import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/logs_screen.dart';
import 'package:auto_invest_dashboard/models/auto_exit_candidate.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/position_exit_review.dart';
import 'package:auto_invest_dashboard/models/position_lifecycle.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_promotion.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_scheduler.dart';

import 'auto_buy_operations_model_test.dart';
import 'auto_buy_promotion_model_test.dart';
import 'auto_buy_scheduler_model_test.dart';

void main() {
  testWidgets('Logs owns detailed run and order history after Home is compact',
      (tester) async {
    final api = _LogsHistoryApiClient();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: LogsScreen(controller: controller)),
    ));
    await tester.pumpAndSettle();

    expect(api.recentRunsLimit, 50);
    expect(api.recentOrdersLimit, 50);
    expect(api.recentSignalsLimit, 50);
    expect(find.text('기록'), findsOneWidget);
    await _showLogsFinder(tester, find.text('Activity Timeline'));
    expect(find.text('Activity Timeline'), findsOneWidget);
    expect(find.textContaining('AAPL - HOLD'), findsOneWidget);

    await tester.tap(find.text('Orders').last);
    await tester.pumpAndSettle();

    expect(find.textContaining('MSFT - BUY'), findsOneWidget);
    await tester.tap(find.text('Advanced Details').last);
    await tester.pumpAndSettle();

    expect(find.textContaining('broker-1'), findsOneWidget);

    controller.dispose();
  });
}

Future<void> _showLogsFinder(WidgetTester tester, Finder finder) async {
  await tester.dragUntilVisible(
    finder,
    find.byType(Scrollable).first,
    const Offset(0, -360),
    maxIteration: 30,
  );
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

class _LogsHistoryApiClient extends ApiClient {
  int? recentRunsLimit;
  int? recentOrdersLimit;
  int? recentSignalsLimit;

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    recentRunsLimit = limit;
    return [
      const TradingLogItem(
        id: 1,
        runKey: 'run-1',
        symbol: 'AAPL',
        triggerSource: 'scheduler',
        mode: 'watchlist',
        action: 'hold',
        result: 'skipped',
        reason: 'weak_signal',
        relatedOrderId: null,
        createdAt: '2026-06-26T01:00:00Z',
        gateLevel: 2,
      ),
    ];
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    recentOrdersLimit = limit;
    return [
      const OrderLogItem(
        id: 1,
        symbol: 'MSFT',
        side: 'buy',
        qty: 1,
        notional: 100,
        brokerOrderId: 'broker-1',
        brokerStatus: 'filled',
        internalStatus: 'FILLED',
        createdAt: '2026-06-26T01:01:00Z',
        updatedAt: '2026-06-26T01:01:00Z',
      ),
    ];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    recentSignalsLimit = limit;
    return const [];
  }

  @override
  Future<LogsSummary> fetchLogsSummary() async => const LogsSummary(
        latestRun: null,
        latestOrder: null,
        latestSignal: null,
        counts: {'runs': 1, 'orders': 1, 'signals': 0},
      );

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async =>
      KisManualOrderSafetyStatus.safeDefault;

  @override
  Future<StrategyAutoBuyOperationsStatus> fetchStrategyAutoBuyOperationsStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async =>
      StrategyAutoBuyOperationsStatus.fromJson(
        autoBuyOperationsJson(
          stage: 'no_dry_run',
          nextAction: 'run_dry_run',
          ready: false,
        ),
      );

  @override
  Future<StrategyAutoBuySchedulerStatus> fetchStrategyAutoBuySchedulerStatus({
    String provider = 'kis',
    String market = 'KR',
  }) async =>
      StrategyAutoBuySchedulerStatus.fromJson(
        autoBuySchedulerStatusJson(),
      );

  @override
  Future<StrategyAutoBuyPromotions> fetchStrategyAutoBuyPromotions({
    String provider = 'kis',
    String market = 'KR',
    String status = 'pending',
    String? symbol,
    int limit = 20,
  }) async =>
      StrategyAutoBuyPromotions.fromJson(autoBuyPromotionsJson());

  @override
  Future<PositionExitReview> fetchPositionExitReview() async =>
      PositionExitReview.fromJson(_positionExitReviewJson());

  @override
  Future<AutoExitCandidates> fetchAutoExitCandidates({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    bool includeDetails = true,
    String? minSeverity,
  }) async =>
      AutoExitCandidates.fromJson(_autoExitCandidatesJson());

  @override
  Future<PositionLifecycle> fetchPositionLifecycle({
    String? symbol,
    String provider = 'kis',
    String market = 'KR',
    String status = 'all',
    int limit = 50,
    bool includeEvents = true,
  }) async =>
      PositionLifecycle.fromJson(_positionLifecycleJson());
}

Map<String, dynamic> _autoExitCandidatesJson() {
  return {
    'generated_at': '2026-07-07T00:00:00Z',
    'timezone': 'Asia/Seoul',
    'provider': 'kis',
    'market': 'KR',
    'candidates': const [],
    'summary': const {
      'candidate_count': 0,
      'critical_count': 0,
      'warning_count': 0,
      'info_count': 0,
      'stop_loss_count': 0,
      'take_profit_count': 0,
      'trend_breakdown_count': 0,
      'manual_review_count': 0,
      'duplicate_sell_block_count': 0,
      'sync_required_count': 0,
    },
    'safety_flags': const ['read_only', 'no_live_orders'],
  };
}

Map<String, dynamic> _positionExitReviewJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'positions': const [],
    'total_position_value': 0,
    'total_unrealized_pl': 0,
    'total_unrealized_pl_pct': null,
    'updated_at': '2026-07-03T00:00:00Z',
    'safety_flags': const ['read_only', 'preflight_only'],
    'safety': const {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
  };
}

Map<String, dynamic> _positionLifecycleJson() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'generated_at': '2026-07-03T00:00:00Z',
    'items': const [],
    'totals': const {
      'open_position_count': 0,
      'closed_lifecycle_count': 0,
      'total_current_value': 0,
      'total_unrealized_pl': 0,
      'total_realized_pl': 0,
      'total_realized_pl_pct': null,
      'incomplete_calculation_count': 0,
    },
    'safety': const {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
    'audit_flags': const ['read_only_lifecycle'],
  };
}
