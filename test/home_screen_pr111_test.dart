import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/theme/app_theme.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/home/home_screen.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  testWidgets('home exposes an explicit account loading state', (tester) async {
    final controller = _controller();

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(
      find.byKey(const ValueKey('home-account-connection-status')),
      findsOneWidget,
    );
    expect(find.text('₩0'), findsNothing);
    expect(
      find.byKey(const ValueKey('home-account-connection-retry')),
      findsNothing,
    );

    controller.dispose();
  });

  testWidgets('home exposes connected state and loaded portfolio values',
      (tester) async {
    final controller = _controller()
      ..portfolioLoaded = true
      ..portfolioLoadedAt = DateTime(2026, 8, 28, 14, 30)
      ..krPortfolioSummary = _summary;

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(find.text('한국투자증권 연결됨'), findsOneWidget);
    expect(find.text('₩1734567'), findsOneWidget);
    expect(find.text('평가금액'), findsOneWidget);
    await tester.drag(find.byType(ListView), const Offset(0, -500));
    await tester.pump();
    expect(find.textContaining('삼성전자 장기 투자 포지션'), findsOneWidget);
    expect(tester.takeException(), isNull);

    controller.dispose();
  });

  testWidgets(
      'Home uses current_operation_mode instead of stale facade paper mode',
      (tester) async {
    final controller = _controller()
      ..setAppLanguage(AppLanguage.english)
      ..settings = _opsSettings('full_live_test_mode');

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(find.text('Live'), findsOneWidget);
    expect(find.text('Paper'), findsNothing);

    controller.dispose();
  });

  testWidgets('canceling the Live confirmation sends no preset request',
      (tester) async {
    final api = _ModeFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..setAppLanguage(AppLanguage.english)
      ..settings = _opsSettings('dry_run_simulation');

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));
    await tester
        .tap(find.byKey(const ValueKey('home-operation-mode-selector')));
    await tester.pumpAndSettle();
    await tester.tap(
        find.byKey(const ValueKey('home-operation-mode-full_live_test_mode')));
    await tester.tap(find.byKey(const ValueKey('home-operation-mode-apply')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();

    expect(api.lastPreset, isNull);
    expect(controller.settings.currentOperationMode, 'dry_run_simulation');

    controller.dispose();
  });
  testWidgets('Home mode selector confirms Live and uses preset endpoint',
      (tester) async {
    final api = _ModeFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..setAppLanguage(AppLanguage.english)
      ..settings = _opsSettings('dry_run_simulation');

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));
    await tester
        .tap(find.byKey(const ValueKey('home-operation-mode-selector')));
    await tester.pumpAndSettle();
    await tester.tap(
        find.byKey(const ValueKey('home-operation-mode-full_live_test_mode')));
    await tester.tap(find.byKey(const ValueKey('home-operation-mode-apply')));
    await tester.pumpAndSettle();

    expect(api.lastPreset, isNull);
    await tester
        .tap(find.byKey(const ValueKey('home-operation-mode-live-confirm')));
    await tester.pumpAndSettle();

    expect(api.lastPreset, 'full_live_test_mode');
    expect(api.lastConfirmDangerous, isTrue);
    expect(controller.settings.currentOperationMode, 'full_live_test_mode');

    controller.dispose();
  });
  testWidgets('home shows retry affordance when account loading fails',
      (tester) async {
    final controller = _controller()
      ..portfolioLoadError = 'fake broker failure';

    await tester.pumpWidget(_app(HomeScreen(controller: controller)));

    expect(
      find.byKey(const ValueKey('home-account-connection-status')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('home-account-connection-retry')),
      findsOneWidget,
    );
    expect(find.text('다시 시도'), findsOneWidget);

    controller.dispose();
  });
}

Widget _app(Widget child) {
  return MaterialApp(
    theme: AppTheme.darkTheme,
    home: child,
  );
}

DashboardController _controller() =>
    DashboardController(_FakeApiClient(), autoload: false);

const _summary = PortfolioSummary(
  currency: 'KRW',
  positionsCount: 1,
  pendingOrdersCount: 0,
  totalCostBasis: 1200000,
  totalMarketValue: 1234567,
  totalUnrealizedPl: 34567,
  totalUnrealizedPlpc: 2.88,
  cash: 500000,
  positions: [
    PositionSummary(
      symbol: '005930',
      name: '삼성전자 장기 투자 포지션',
      side: 'long',
      qty: 2,
      avgEntryPrice: 600000,
      costBasis: 1200000,
      currentPrice: 617283.5,
      marketValue: 1234567,
      unrealizedPl: 34567,
      unrealizedPlpc: 2.88,
    ),
  ],
  pendingOrders: [],
);

class _FakeApiClient extends ApiClient {
  _FakeApiClient() : super(client: _FakeHttpClient());
}

class _FakeHttpClient extends http.BaseClient {
  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      Future<http.StreamedResponse>.error(
        StateError('network is intentionally unavailable in this UI test'),
      );
}

OpsSettings _opsSettings(String currentOperationMode) => OpsSettings(
      schedulerEnabled: true,
      botEnabled: true,
      dryRun: currentOperationMode != 'full_live_test_mode',
      killSwitch: false,
      brokerMode: 'Paper',
      defaultGateLevel: 2,
      maxDailyTrades: 5,
      maxDailyEntries: 2,
      minEntryScore: 65,
      minScoreGap: 3,
      currentOperationMode: currentOperationMode,
      kisSchedulerEnabled: true,
      kisSchedulerDryRun: currentOperationMode != 'full_live_test_mode',
      kisSchedulerLiveEnabled: currentOperationMode == 'full_live_test_mode',
      kisSchedulerAllowRealOrders:
          currentOperationMode == 'full_live_test_mode',
      kisSchedulerBuyEnabled: currentOperationMode == 'full_live_test_mode',
      kisSchedulerSellEnabled: currentOperationMode == 'full_live_test_mode',
    );

class _ModeFakeApiClient extends _FakeApiClient {
  String? lastPreset;
  bool? lastConfirmDangerous;

  @override
  Future<Map<String, dynamic>> applyOpsSettingsPreset({
    required String preset,
    bool confirmDangerous = false,
  }) async {
    lastPreset = preset;
    lastConfirmDangerous = confirmDangerous;
    return const {'applied': true};
  }

  @override
  Future<OpsSettings> getOpsSettings() async =>
      _opsSettings(lastPreset ?? 'dry_run_simulation');
}
