import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/strategy_risk.dart';

import 'strategy_risk_model_test.dart';

void main() {
  test('refresh strategy risk uses risk-state endpoint only', () async {
    final api = _RiskApiClient();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshStrategyRiskState();

    expect(result.success, isTrue);
    expect(api.fetchCalls, 1);
    expect(api.mutationCalls, 0);
    expect(controller.strategyRiskState?.activeProfile, 'balanced');
    expect(controller.strategyRiskState?.newEntriesAllowed, isTrue);
    expect(controller.strategyRiskError, isNull);

    controller.dispose();
  });
}

class _RiskApiClient extends ApiClient {
  int fetchCalls = 0;
  int mutationCalls = 0;

  @override
  Future<StrategyRiskState> fetchStrategyRiskState({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    fetchCalls += 1;
    return StrategyRiskState.fromJson(strategyRiskJson());
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    mutationCalls += 1;
    throw StateError('risk refresh must not update settings');
  }
}
