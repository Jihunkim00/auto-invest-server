import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/strategy_live_auto_exit.dart';

import 'strategy_live_auto_exit_model_test.dart';

void main() {
  test('run guarded live auto exit uses one-shot endpoint only when ready',
      () async {
    final api = _LiveAutoExitApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyLiveAutoExit(silent: true);

    final result = await controller.runStrategyLiveAutoExitOnce();

    expect(result.success, isTrue);
    expect(api.readinessCalls, 2);
    expect(api.runCalls, 1);
    expect(api.recentCalls, 2);
    expect(api.mutationCalls, 0);
    expect(controller.strategyLiveAutoExitResult?.submitted, isTrue);
    expect(controller.strategyLiveAutoExitRecent, hasLength(1));
    expect(controller.strategyLiveAutoExitError, isNull);
    controller.dispose();
  });

  test('run guarded live auto exit is blocked locally when readiness is false',
      () async {
    final api = _LiveAutoExitApiClient(ready: false);
    final controller = DashboardController(api, autoload: false);
    await controller.refreshStrategyLiveAutoExit(silent: true);

    final result = await controller.runStrategyLiveAutoExitOnce();

    expect(result.success, isFalse);
    expect(result.message, contains('strategy_live_auto_exit_disabled'));
    expect(api.runCalls, 0);
    expect(api.mutationCalls, 0);
    controller.dispose();
  });
}

class _LiveAutoExitApiClient extends ApiClient {
  _LiveAutoExitApiClient({this.ready = true});

  final bool ready;
  int readinessCalls = 0;
  int runCalls = 0;
  int recentCalls = 0;
  int mutationCalls = 0;

  @override
  Future<StrategyLiveAutoExitReadiness> fetchStrategyLiveAutoExitReadiness({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
  }) async {
    readinessCalls += 1;
    return StrategyLiveAutoExitReadiness.fromJson(
      liveExitReadinessJson(ready: ready),
    );
  }

  @override
  Future<StrategyLiveAutoExitRunResult> runStrategyLiveAutoExitOnce({
    String provider = 'kis',
    String market = 'KR',
    String? symbol,
    int? quantity,
    String triggerSource = 'flutter_dashboard',
    String? clientRequestId,
  }) async {
    runCalls += 1;
    return StrategyLiveAutoExitRunResult.fromJson(
      liveExitRunResultJson(status: 'submitted', submitted: true),
    );
  }

  @override
  Future<StrategyLiveAutoExitRecent> fetchStrategyLiveAutoExitRecent({
    String provider = 'kis',
    String market = 'KR',
    int limit = 20,
  }) async {
    recentCalls += 1;
    final item = StrategyLiveAutoExitRunResult.fromJson(
      liveExitRunResultJson(status: 'submitted', submitted: true),
    );
    return StrategyLiveAutoExitRecent(
      provider: provider,
      market: market,
      items: [item],
      safety: const {'read_only': true},
    );
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    mutationCalls += 1;
    throw StateError('guarded live auto exit must not update settings');
  }
}
