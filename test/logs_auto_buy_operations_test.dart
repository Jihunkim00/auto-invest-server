import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/logs_screen.dart';
import 'package:auto_invest_dashboard/models/auto_exit_candidate.dart';
import 'package:auto_invest_dashboard/models/daily_ops_summary.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/operator_alerts.dart';
import 'package:auto_invest_dashboard/models/position_exit_review.dart';
import 'package:auto_invest_dashboard/models/position_lifecycle.dart';
import 'package:auto_invest_dashboard/models/position_management_dry_run.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_operations.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_promotion.dart';
import 'package:auto_invest_dashboard/models/strategy_auto_buy_scheduler.dart';

import 'auto_buy_operations_model_test.dart';
import 'auto_buy_promotion_model_test.dart';
import 'auto_buy_scheduler_model_test.dart';
import 'daily_ops_summary_model_test.dart';
import 'operator_alerts_model_test.dart';

void main() {
  testWidgets('Logs screen loads and shows auto buy operations panel',
      (tester) async {
    final api = _LogsAutoBuyOpsApiClient();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: LogsScreen(controller: controller)),
    ));
    await tester.pumpAndSettle();

    expect(api.operationsCalls, 1);
    expect(api.recentRunsLimit, 50);
    expect(find.text('기록'), findsOneWidget);
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('auto-buy-operations-panel')),
      500,
    );
    await tester.pumpAndSettle();
    expect(find.text('자동매수 운영'), findsWidgets);
    expect(find.text('자동매수 운영'), findsWidgets);
    expect(find.text('드라이런 자동매수 1회 실행'), findsOneWidget);
    expect(find.text('보호된 실매수 1회 실행'), findsOneWidget);
    expect(find.text('Enable Scheduler'), findsNothing);
    expect(find.text('Turn Off Dry Run'), findsNothing);
    expect(find.text('Disable Kill Switch'), findsNothing);
    expect(find.text('Enable KIS Real Order'), findsNothing);
    expect(find.text('Retry Submit'), findsNothing);
    expect(find.text('Submit Again'), findsNothing);

    controller.dispose();
  });
}

class _LogsAutoBuyOpsApiClient extends ApiClient {
  int operationsCalls = 0;
  int? recentRunsLimit;

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    recentRunsLimit = limit;
    return const [];
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    return const [];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    return const [];
  }

  @override
  Future<LogsSummary> fetchLogsSummary() async => const LogsSummary(
        latestRun: null,
        latestOrder: null,
        latestSignal: null,
        counts: {'runs': 0, 'orders': 0, 'signals': 0},
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
  }) async {
    operationsCalls += 1;
    return StrategyAutoBuyOperationsStatus.fromJson(autoBuyOperationsJson());
  }

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
  Future<OperatorAlerts> fetchOperatorAlerts({
    String provider = 'kis',
    String market = 'KR',
    String severity = 'all',
    String status = 'active',
    int limit = 50,
    bool includeDetails = true,
  }) async =>
      OperatorAlerts.fromJson(operatorAlertsJson(
        provider: provider,
        market: market,
      ));

  @override
  Future<DailyOpsSummary> fetchDailyOpsSummary({
    String provider = 'kis',
    String market = 'KR',
    String? date,
    bool includeDetails = true,
  }) async =>
      DailyOpsSummary.fromJson(
        dailyOpsSummaryJson(provider: provider, market: market),
      );

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
  Future<PositionManagementDryRun> fetchPositionManagementDryRunLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async =>
      PositionManagementDryRun.fromJson(
        _positionManagementDryRunJson(provider: provider, market: market),
      );

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

Map<String, dynamic> _positionManagementDryRunJson({
  String provider = 'kis',
  String market = 'KR',
}) {
  return {
    'run_id': null,
    'generated_at': '2026-07-07T00:00:00Z',
    'provider': provider,
    'market': market,
    'trigger_source': 'position_management_dry_run_latest_lookup',
    'dry_run_only': true,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'positions_checked': 0,
    'exit_candidate_count': 0,
    'critical_candidate_count': 0,
    'warning_candidate_count': 0,
    'simulated_sell_preflight_count': 0,
    'blocked_preflight_count': 0,
    'sync_required_count': 0,
    'duplicate_sell_conflict_count': 0,
    'result_status': 'skipped',
    'primary_reason': 'no_recent_position_management_dry_run',
    'risk_flags': const ['no_recent_run'],
    'gating_notes': const [
      'No position management dry-run has been recorded yet.'
    ],
    'candidates': const [],
    'sell_preflight_results': const [],
    'next_safe_actions': const ['Continue monitoring held positions.'],
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
