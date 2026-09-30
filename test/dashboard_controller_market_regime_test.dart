import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/market_regime.dart';

void main() {
  test('KIS dashboard load requests and keeps the persisted regime response',
      () async {
    final api = _MarketRegimeApiClient();
    final controller = DashboardController(api, autoload: false);
    await controller.loadMarketRegime();

    expect(api.calls, 1);
    expect(controller.marketRegime?.marketScore, 61.23);
    expect(controller.marketRegimeError, isNull);
    controller.dispose();
  });

  test('Alpaca selection clears regime and does not request the endpoint',
      () async {
    final api = _MarketRegimeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.alpaca;
    await controller.loadMarketRegime();

    expect(api.calls, 0);
    expect(controller.marketRegime, isNull);
    controller.dispose();
  });

  test('endpoint failure is isolated from dashboard state', () async {
    final api = _MarketRegimeApiClient(throws: true);
    final controller = DashboardController(api, autoload: false);
    await controller.loadMarketRegime();

    expect(controller.marketRegime, isNull);
    expect(controller.marketRegimeLoaded, isTrue);
    expect(controller.marketRegimeError, isNotNull);
    expect(controller.error, isNull);
    controller.dispose();
  });
}

class _MarketRegimeApiClient extends ApiClient {
  _MarketRegimeApiClient({this.throws = false});

  final bool throws;
  int calls = 0;

  @override
  Future<MarketRegime> fetchMarketRegime() async {
    calls += 1;
    if (throws) throw StateError('endpoint unavailable');
    return MarketRegime.fromJson({
      'status': 'confirmed',
      'stage': 4,
      'stage_label': '상승 진행',
      'short_label': '상승',
      'market_score': 61.23,
      'confirmed': true,
    });
  }
}
