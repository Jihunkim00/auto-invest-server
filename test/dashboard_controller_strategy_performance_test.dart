import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/strategy_performance.dart';

import 'strategy_performance_fixtures.dart';

void main() {
  test('refresh strategy performance uses read-only endpoints only', () async {
    final api = _PerformanceApiClient();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshStrategyPerformance();

    expect(result.success, isTrue);
    expect(api.dailyCalls, 1);
    expect(api.monthlyCalls, 1);
    expect(api.tradeCalls, 1);
    expect(api.mutationCalls, 0);
    expect(controller.strategyDailyPerformance?.netPnlEstimated, 9500);
    expect(controller.strategyMonthlyPerformance?.targetProgressPct, 66.7);
    expect(controller.strategyTradePerformance?.count, 1);
    expect(controller.strategyPerformanceError, isNull);

    controller.dispose();
  });

  test('refresh strategy performance reports endpoint failure', () async {
    final api = _PerformanceApiClient(throwMonthly: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshStrategyPerformance();

    expect(result.success, isFalse);
    expect(controller.strategyPerformanceLoading, isFalse);
    expect(
        controller.strategyPerformanceError, contains('monthly unavailable'));
    expect(api.mutationCalls, 0);

    controller.dispose();
  });
}

class _PerformanceApiClient extends ApiClient {
  _PerformanceApiClient({this.throwMonthly = false});

  final bool throwMonthly;
  int dailyCalls = 0;
  int monthlyCalls = 0;
  int tradeCalls = 0;
  int mutationCalls = 0;

  @override
  Future<StrategyDailyPerformance> fetchStrategyDailyPerformance({
    String provider = 'kis',
    String market = 'KR',
    String? date,
  }) async {
    dailyCalls += 1;
    return StrategyDailyPerformance.fromJson(strategyDailyPerformanceJson());
  }

  @override
  Future<StrategyMonthlyPerformance> fetchStrategyMonthlyPerformance({
    String provider = 'kis',
    String market = 'KR',
    String? month,
  }) async {
    monthlyCalls += 1;
    if (throwMonthly) {
      throw const ApiRequestException('monthly unavailable');
    }
    return StrategyMonthlyPerformance.fromJson(
      strategyMonthlyPerformanceJson(),
    );
  }

  @override
  Future<StrategyTradePerformanceList> fetchStrategyTradePerformance({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int limit = 20,
  }) async {
    tradeCalls += 1;
    return StrategyTradePerformanceList.fromJson(
      strategyTradePerformanceJson(),
    );
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    mutationCalls += 1;
    throw StateError('performance refresh must not update settings');
  }
}
