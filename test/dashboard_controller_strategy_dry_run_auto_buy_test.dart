import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/strategy_dry_run_auto_buy.dart';

import 'strategy_dry_run_auto_buy_model_test.dart';

void main() {
  test('run dry-run button uses strategy dry-run endpoints only', () async {
    final api = _DryRunApiClient();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runStrategyDryRunAutoBuy();

    expect(result.success, isTrue);
    expect(api.runCalls, 1);
    expect(api.recentCalls, 1);
    expect(api.mutationCalls, 0);
    expect(controller.strategyDryRunAutoBuyResult?.action, 'would_buy');
    expect(controller.strategyDryRunAutoBuyRecent, hasLength(1));
    expect(controller.strategyDryRunAutoBuyError, isNull);
    controller.dispose();
  });
}

class _DryRunApiClient extends ApiClient {
  int runCalls = 0;
  int recentCalls = 0;
  int mutationCalls = 0;

  @override
  Future<StrategyDryRunAutoBuyResult> runStrategyDryRunAutoBuy({
    String? profileName,
    String? symbol,
  }) async {
    runCalls += 1;
    return StrategyDryRunAutoBuyResult.fromJson(dryRunResultJson());
  }

  @override
  Future<StrategyDryRunAutoBuyRecent> fetchStrategyDryRunAutoBuyRecent({
    String provider = 'kis',
    String market = 'KR',
    String? profileName,
    String? symbol,
    int limit = 20,
  }) async {
    recentCalls += 1;
    return StrategyDryRunAutoBuyRecent.fromJson({
      'provider': 'kis',
      'market': 'KR',
      'count': 1,
      'items': [dryRunResultJson()],
      'safety': {'dry_run_only': true},
    });
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    mutationCalls += 1;
    throw StateError('dry-run must not update settings');
  }
}
