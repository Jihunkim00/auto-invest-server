import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_buy.dart';

import 'strategy_live_auto_buy_model_test.dart';

void main() {
  test('run guarded live auto buy uses one-shot endpoint only when ready',
      () async {
    final api = _LiveAutoBuyApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyLiveAutoBuy(silent: true);

    final result = await controller.runStrategyLiveAutoBuyOnce();

    expect(result.success, isTrue);
    expect(api.readinessCalls, 2);
    expect(api.runCalls, 1);
    expect(api.recentCalls, 2);
    expect(api.mutationCalls, 0);
    expect(controller.strategyLiveAutoBuyResult?.submitted, isTrue);
    expect(controller.strategyLiveAutoBuyRecent, hasLength(1));
    expect(controller.strategyLiveAutoBuyError, isNull);
    controller.dispose();
  });

  test('run guarded live auto buy is blocked locally when readiness is false',
      () async {
    final api = _LiveAutoBuyApiClient(ready: false);
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyLiveAutoBuy(silent: true);

    final result = await controller.runStrategyLiveAutoBuyOnce();

    expect(result.success, isFalse);
    expect(result.message, contains('strategy_live_auto_buy_disabled'));
    expect(api.runCalls, 0);
    expect(api.mutationCalls, 0);
    controller.dispose();
  });

  test('sync guarded live auto buy result uses sync endpoint only', () async {
    final api = _LiveAutoBuyApiClient();
    final controller = DashboardController(api, autoload: false);
    final result = StrategyLiveAutoBuyResult.fromJson(
      liveResultJson(
        resultStatus: 'pending_sync',
        internalStatus: 'UNKNOWN_STALE',
      ),
    );

    final action = await controller.syncGuardedLiveAutoBuyResult(result);

    expect(action.success, isTrue);
    expect(api.resultSyncCalls, 1);
    expect(api.resultFetchCalls, 0);
    expect(api.runCalls, 0);
    expect(api.mutationCalls, 0);
    expect(
        controller.latestStrategyLiveAutoBuyConversionResult?.filled, isTrue);
    controller.dispose();
  });
}

class _LiveAutoBuyApiClient extends ApiClient {
  _LiveAutoBuyApiClient({this.ready = true});

  final bool ready;
  int readinessCalls = 0;
  int runCalls = 0;
  int recentCalls = 0;
  int resultFetchCalls = 0;
  int resultSyncCalls = 0;
  int mutationCalls = 0;

  @override
  Future<StrategyLiveAutoBuyReadiness> fetchStrategyLiveAutoBuyReadiness({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? sourceDryRunId,
  }) async {
    readinessCalls += 1;
    return StrategyLiveAutoBuyReadiness.fromJson(
      liveReadinessJson(ready: ready),
    );
  }

  @override
  Future<StrategyLiveAutoBuyRunResult> runStrategyLiveAutoBuyOnce({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? promotionId,
    int? sourceDryRunId,
    double? maxNotionalKrw,
    String triggerSource = 'flutter_dashboard',
    String? clientRequestId,
  }) async {
    runCalls += 1;
    return StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(status: 'submitted', submitted: true),
    );
  }

  @override
  Future<StrategyLiveAutoBuyRecent> fetchStrategyLiveAutoBuyRecent({
    String provider = 'kis',
    String market = 'KR',
    int limit = 20,
  }) async {
    recentCalls += 1;
    final item = StrategyLiveAutoBuyRunResult.fromJson(
      liveRunResultJson(status: 'submitted', submitted: true),
    );
    return StrategyLiveAutoBuyRecent(
      provider: provider,
      market: market,
      items: [item],
      safety: const {'read_only': true},
    );
  }

  @override
  Future<StrategyLiveAutoBuyResult> fetchStrategyLiveAutoBuyResult(
    int attemptId,
  ) async {
    resultFetchCalls += 1;
    return StrategyLiveAutoBuyResult.fromJson(liveResultJson());
  }

  @override
  Future<StrategyLiveAutoBuyResult> syncStrategyLiveAutoBuyResult(
    int attemptId,
  ) async {
    resultSyncCalls += 1;
    return StrategyLiveAutoBuyResult.fromJson(
      liveResultJson(resultStatus: 'filled', internalStatus: 'FILLED'),
    );
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    mutationCalls += 1;
    throw StateError('guarded live auto buy must not update settings');
  }
}
