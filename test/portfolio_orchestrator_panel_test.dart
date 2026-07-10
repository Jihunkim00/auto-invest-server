import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/logs/widgets/portfolio_orchestrator_panel.dart';
import 'package:auto_invest_dashboard/models/portfolio_orchestrator.dart';

import 'portfolio_orchestrator_model_test.dart';

void main() {
  testWidgets('panel renders Korean safe default labels', (tester) async {
    _setLargeViewport(tester);
    final controller = _controller(portfolioOrchestratorJson());

    await _pumpPanel(tester, controller);

    expect(
      find.byKey(const ValueKey('portfolio-orchestrator-panel')),
      findsOneWidget,
    );
    expect(find.text('포트폴리오 자동 운영'), findsOneWidget);
    expect(find.text('통합 자동화 루프'), findsOneWidget);
    expect(find.text('보유 종목 점검 먼저'), findsOneWidget);
    expect(find.text('자동매도 우선'), findsOneWidget);
    expect(find.text('자동매수 후순위'), findsOneWidget);
    expect(find.text('기본 비활성화'), findsOneWidget);
    expect(find.text('실행 없음'), findsOneWidget);
    expect(find.text('브로커 제출 없음'), findsWidgets);
    expect(find.text('자동 재시도 없음'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('panel renders English labels and disabled state',
      (tester) async {
    _setLargeViewport(tester);
    final controller = _controller(
      portfolioOrchestratorJson(),
      language: AppLanguage.english,
    );

    await _pumpPanel(tester, controller);

    expect(find.text('Portfolio Orchestrator'), findsOneWidget);
    expect(find.text('Unified Automation Loop'), findsOneWidget);
    expect(find.text('Positions First'), findsOneWidget);
    expect(find.text('Check Positions First'), findsOneWidget);
    expect(find.text('Auto Sell First'), findsOneWidget);
    expect(find.text('Auto Buy Second'), findsOneWidget);
    expect(find.text('Daily Action Limit'), findsOneWidget);
    expect(find.text('Blocked When Sync Required'), findsWidgets);
    expect(find.text('Disabled by Default'), findsWidgets);
    expect(find.text('Run Orchestrator Once'), findsOneWidget);
    expect(find.text('Refresh Orchestrator Status'), findsWidgets);

    controller.dispose();
  });

  testWidgets('run once calls only orchestrator endpoint in monitoring mode',
      (tester) async {
    _setLargeViewport(tester);
    final api = _OrchestratorApiClient(
      PortfolioOrchestratorResult.fromJson(
        portfolioOrchestratorJson(
          enabled: true,
          status: 'dry_run_completed',
        ),
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..portfolioOrchestratorStatus = PortfolioOrchestratorResult.fromJson(
        portfolioOrchestratorJson(),
      );

    await _pumpPanel(tester, controller);
    await tester.tap(
      find.byKey(const ValueKey('run-portfolio-orchestrator-once')),
    );
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.fetchCalls, 0);
    expect(api.otherCalls, 0);
    expect(api.lastProvider, 'kis');
    expect(api.lastMarket, 'KR');
    expect(api.lastTriggerSource, 'manual_orchestrator_test');
    expect(api.lastMode, 'dry_run_monitoring');
    expect(api.lastLanguage, 'ko');
    expect(api.lastLocale, 'ko-KR');

    controller.dispose();
  });

  testWidgets('sell submission shows skipped buy and no buy submission',
      (tester) async {
    _setLargeViewport(tester);
    final controller = _controller(
      portfolioOrchestratorJson(
        enabled: true,
        status: 'sell_submitted',
        action: 'auto_sell_phase1',
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
        skippedBuyReason: 'sell_submitted',
      ),
      language: AppLanguage.english,
    );

    await _pumpPanel(tester, controller);

    expect(find.text('Sell Submitted'), findsOneWidget);
    expect(find.text('Buy Submitted'), findsNothing);
    expect(find.text('Buy Skipped Reason'), findsOneWidget);
    expect(find.text('Live Order Submitted'), findsOneWidget);
    expect(find.text('No Auto Retry'), findsWidgets);

    controller.dispose();
  });

  testWidgets('buy submission displays auto-buy action', (tester) async {
    _setLargeViewport(tester);
    final controller = _controller(
      portfolioOrchestratorJson(
        enabled: true,
        status: 'buy_submitted',
        action: 'auto_buy_phase1',
        realOrderSubmitted: true,
        brokerSubmitCalled: true,
      ),
      language: AppLanguage.english,
    );

    await _pumpPanel(tester, controller);

    expect(find.text('Buy Submitted'), findsOneWidget);
    expect(find.text('Sell Submitted'), findsNothing);
    expect(find.text('Live Order Submitted'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('no-action result shows no broker submit and no unsafe controls',
      (tester) async {
    _setLargeViewport(tester);
    final controller = _controller(
      portfolioOrchestratorJson(
        enabled: true,
        status: 'completed_no_action',
      ),
      language: AppLanguage.english,
    );

    await _pumpPanel(tester, controller);

    expect(find.text('No Action'), findsOneWidget);
    expect(find.text('No Broker Submit'), findsOneWidget);
    for (final forbidden in const [
      'Force Run',
      'Skip Safety Gates',
      'Buy Now',
      'Sell Now',
      'Retry',
      'Liquidate All',
      'Disable Kill Switch',
      'Turn Off Dry Run',
      'Enable KIS Real Orders',
      'Enable Live Scheduler',
      'Enable Full Automation',
    ]) {
      expect(find.text(forbidden), findsNothing, reason: forbidden);
    }

    controller.dispose();
  });

  testWidgets('broker call without confirmed submission is not shown as live',
      (tester) async {
    _setLargeViewport(tester);
    final controller = _controller(
      portfolioOrchestratorJson(
        enabled: true,
        status: 'blocked',
        action: 'auto_buy_phase1',
        brokerSubmitCalled: true,
      ),
      language: AppLanguage.english,
    );

    await _pumpPanel(tester, controller);

    expect(find.text('No Action'), findsOneWidget);
    expect(find.text('Broker Submit Called'), findsOneWidget);
    expect(find.text('Live Order Submitted'), findsNothing);

    controller.dispose();
  });
}

DashboardController _controller(
  Map<String, dynamic> json, {
  AppLanguage language = AppLanguage.korean,
}) {
  final result = PortfolioOrchestratorResult.fromJson(json);
  return DashboardController(
    _OrchestratorApiClient(result),
    autoload: false,
    initialLanguage: language,
  )..portfolioOrchestratorStatus = result;
}

Future<void> _pumpPanel(
  WidgetTester tester,
  DashboardController controller,
) async {
  await tester.pumpWidget(
    MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: PortfolioOrchestratorPanel(controller: controller)),
    ),
  );
  await tester.pump();
}

void _setLargeViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 1800);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

class _OrchestratorApiClient extends ApiClient {
  _OrchestratorApiClient(this.result);

  final PortfolioOrchestratorResult result;
  int fetchCalls = 0;
  int runCalls = 0;
  int otherCalls = 0;
  String? lastProvider;
  String? lastMarket;
  String? lastTriggerSource;
  String? lastMode;
  String? lastLanguage;
  String? lastLocale;

  @override
  Future<PortfolioOrchestratorResult> fetchPortfolioOrchestratorLatest({
    String provider = 'kis',
    String market = 'KR',
  }) async {
    fetchCalls += 1;
    return result;
  }

  @override
  Future<PortfolioOrchestratorResult> runPortfolioOrchestratorOnce({
    String provider = 'kis',
    String market = 'KR',
    String triggerSource = 'manual_orchestrator_test',
    String mode = 'dry_run_monitoring',
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    runCalls += 1;
    lastProvider = provider;
    lastMarket = market;
    lastTriggerSource = triggerSource;
    lastMode = mode;
    lastLanguage = language;
    lastLocale = locale;
    return result;
  }
}
