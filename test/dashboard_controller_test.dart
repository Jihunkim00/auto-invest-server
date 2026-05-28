import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:auto_invest_dashboard/models/kis_auto_readiness.dart';
import 'package:auto_invest_dashboard/models/kis_buy_shadow_decision.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_buy.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_sell.dart';
import 'package:auto_invest_dashboard/models/kis_live_exit_preflight.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_buy.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_live.dart';
import 'package:auto_invest_dashboard/models/kis_shadow_exit_review.dart';
import 'package:auto_invest_dashboard/models/kis_shadow_exit_review_queue.dart';
import 'package:auto_invest_dashboard/models/kis_single_symbol_trading_result.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

void main() {
  test('load uses latest backend watchlist result without mock overwrite',
      () async {
    final api = _FakeApiClient(latest: _resultFor('NVDA'));
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.hasLatestRunResult, isTrue);
    expect(controller.showingOfflineFallback, isFalse);
    expect(controller.runResult.finalBestCandidate, 'NVDA');
    expect(api.mockCalls, 0);

    controller.dispose();
  });

  test('load keeps neutral state when backend has no watchlist run', () async {
    final api = _FakeApiClient();
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.hasLatestRunResult, isFalse);
    expect(controller.showingOfflineFallback, isFalse);
    expect(controller.runResult.finalBestCandidate, isEmpty);
    expect(api.mockCalls, 0);

    controller.dispose();
  });

  test('load uses labeled mock fallback only when latest fetch fails',
      () async {
    final api = _FakeApiClient(throwLatest: true);
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.hasLatestRunResult, isFalse);
    expect(controller.showingOfflineFallback, isTrue);
    expect(controller.runResult.finalBestCandidate, 'MOCK');
    expect(api.mockCalls, greaterThanOrEqualTo(1));

    controller.dispose();
  });

  test('refreshAutomationRuntimeMonitor tolerates partial endpoint failure',
      () async {
    final api = _FakeApiClient(
      recentRuns: [_alpacaSchedulerRun()],
      throwRecentOrders: true,
      guardedSell: _guardedSellStatus(),
      guardedBuy: _guardedBuyStatus(),
    );
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshAutomationRuntimeMonitor();

    expect(result.success, isFalse);
    expect(controller.automationRuntimeMonitor, isNotNull);
    expect(controller.automationRuntimeMonitorError,
        contains('recent orders unavailable'));
    expect(controller.automationRuntimeMonitor!.alpaca.lastResult, 'skipped');
    expect(controller.automationRuntimeMonitor!.kis.lastTriggerDetected,
        'take_profit');
    expect(api.fetchRecentRunsCalls, 1);
    expect(api.fetchRecentOrdersCalls, 1);
    expect(api.fetchRecentSignalsCalls, 1);

    controller.dispose();
  });

  test('refreshPortfolioManagement builds sorted held-position items',
      () async {
    final api = _FakeApiClient(
      krPortfolio: PortfolioSummary(
        currency: 'KRW',
        positionsCount: 3,
        pendingOrdersCount: 0,
        totalCostBasis: 3000,
        totalMarketValue: 2900,
        totalUnrealizedPl: -100,
        totalUnrealizedPlpc: -0.03,
        cash: 0,
        positions: const [
          PositionSummary(
            symbol: '000003',
            name: 'Hold',
            side: 'long',
            qty: 1,
            avgEntryPrice: 1000,
            costBasis: 1000,
            currentPrice: 1000,
            marketValue: 1000,
            unrealizedPl: 0,
            unrealizedPlpc: 0,
          ),
          PositionSummary(
            symbol: '000002',
            name: 'Take Profit',
            side: 'long',
            qty: 1,
            avgEntryPrice: 1000,
            costBasis: 1000,
            currentPrice: 1200,
            marketValue: 1200,
            unrealizedPl: 200,
            unrealizedPlpc: 0.2,
          ),
          PositionSummary(
            symbol: '000001',
            name: 'Stop Loss',
            side: 'long',
            qty: 1,
            avgEntryPrice: 1000,
            costBasis: 1000,
            currentPrice: 700,
            marketValue: 700,
            unrealizedPl: -300,
            unrealizedPlpc: -0.3,
          ),
        ],
        pendingOrders: const [],
      ),
      managedPositions: [
        _managedPosition(
          symbol: '000003',
          holdingStatus: 'HOLD',
          stopLossTriggered: false,
          manualReviewRequired: false,
        ),
        _managedPosition(
          symbol: '000002',
          stopLossTriggered: false,
          takeProfitTriggered: true,
          holdingStatus: 'SELL_READY',
        ),
        _managedPosition(
          symbol: '000001',
          stopLossTriggered: true,
          holdingStatus: 'SELL_READY',
        ),
      ],
    );
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshPortfolioManagement();

    expect(result.success, isTrue);
    final krItems = controller.portfolioManagementItemsForMarket(
      PortfolioMarket.kr,
    );
    expect(krItems.map((item) => item.symbol), ['000001', '000002', '000003']);
    expect(krItems.first.triggerStatus.label, 'STOP_LOSS_READY');
    expect(krItems[1].triggerStatus.label, 'TAKE_PROFIT_READY');
    expect(krItems.last.triggerStatus.label, 'HOLD');

    controller.dispose();
  });

  test('portfolio market defaults to US and keeps summaries separate',
      () async {
    final api = _FakeApiClient(
      usPortfolio: _portfolio('USD', marketValue: 1200),
      krPortfolio: _portfolio('KRW', marketValue: 2500000),
    );
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.selectedPortfolioMarket, PortfolioMarket.us);
    expect(controller.selectedPortfolioSummary.currency, 'USD');
    expect(controller.selectedPortfolioSummary.totalMarketValue, 1200);

    controller.selectPortfolioMarket(PortfolioMarket.kr);

    expect(controller.selectedPortfolioSummary.currency, 'KRW');
    expect(controller.selectedPortfolioSummary.totalMarketValue, 2500000);
    expect(controller.usPortfolioSummary.totalMarketValue, 1200);
    expect(controller.krPortfolioSummary.totalMarketValue, 2500000);

    controller.dispose();
  });

  test('KR portfolio unavailable does not crash dashboard state', () async {
    final api = _FakeApiClient(throwKrPortfolio: true);
    final controller = DashboardController(api, autoload: false);

    await controller.load();
    controller.selectPortfolioMarket(PortfolioMarket.kr);

    expect(controller.krPortfolioUnavailable, isTrue);
    expect(controller.selectedPortfolioUnavailable, isTrue);
    expect(controller.selectedPortfolioSummary.currency, 'KRW');
    expect(controller.selectedPortfolioSummary.positions, isEmpty);

    controller.dispose();
  });

  test('watchlist defaults to US and can switch to KR', () async {
    final api = _FakeApiClient(
      usWatchlist: _watchlist('US', const ['AAPL', 'MSFT']),
      krWatchlist: const MarketWatchlist(
        market: 'KR',
        currency: 'KRW',
        timezone: 'Asia/Seoul',
        watchlistFile: 'config/watchlist_kr.yaml',
        count: 1,
        symbols: [
          WatchlistSymbol(
              symbol: '005930', name: 'Samsung Electronics', market: 'KOSPI'),
        ],
      ),
    );
    final controller = DashboardController(api, autoload: false);

    await controller.load();

    expect(controller.selectedWatchlistMarket, PortfolioMarket.us);
    expect(controller.usWatchlist.symbols.first.symbol, 'AAPL');

    controller.selectWatchlistMarket(PortfolioMarket.kr);

    expect(controller.krWatchlist.symbols.first.symbol, '005930');
    expect(controller.krWatchlist.symbols.first.market, 'KOSPI');

    controller.dispose();
  });

  test('KR top 50 update calls backend and refreshes KR watchlist', () async {
    final updatedWatchlist = _watchlist('KR', const ['100001', '100002']);
    final api = _FakeApiClient(updatedKosdaqWatchlist: updatedWatchlist);
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis;

    final result = await controller.updateKosdaqTop50Watchlist();

    expect(result.success, isTrue);
    expect(result.message, 'KR top 50 watchlist updated.');
    expect(api.updateKosdaqTop50WatchlistCalls, 1);
    expect(controller.latestKosdaqTop50Update?['updated'], isTrue);
    expect(controller.krWatchlist.symbols.first.symbol, '100001');
    expect(controller.kosdaqTop50Updating, isFalse);

    controller.dispose();
  });

  test('KIS order validation stays dry-run through API method', () async {
    final api = _FakeApiClient(validationResult: _validationResult());
    final controller = DashboardController(api, autoload: false)
      ..selectOrderMarket(PortfolioMarket.kr)
      ..setOrderTicketSymbol('005930')
      ..setOrderTicketSide('buy')
      ..setOrderTicketQty(1);

    final result = await controller.validateKisOrder();

    expect(result.success, isTrue);
    expect(controller.orderValidationResult?.dryRun, isTrue);
    expect(controller.orderValidationResult?.symbol, '005930');
    expect(api.validationCalls, 1);

    controller.dispose();
  });

  test('successful dry-run update calls backend and refreshes state', () async {
    final api = _FakeApiClient(settingsDryRun: true, refreshedDryRun: false);
    final controller = DashboardController(api, autoload: false);

    await controller.load();
    final result = await controller.setDryRun(false);

    expect(result.success, isTrue);
    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate, {'dry_run': false});
    expect(api.getOpsSettingsCalls, 2);
    expect(controller.settings.dryRun, isFalse);

    controller.dispose();
  });

  test('failed dry-run update rolls back state', () async {
    final api =
        _FakeApiClient(settingsDryRun: true, throwUpdateOpsSettings: true);
    final controller = DashboardController(api, autoload: false);

    await controller.load();
    final result = await controller.setDryRun(false);

    expect(result.success, isFalse);
    expect(api.updateOpsSettingsCalls, 1);
    expect(api.getOpsSettingsCalls, 2);
    expect(controller.settings.dryRun, isTrue);
    expect(controller.dryRunLoading, isFalse);

    controller.dispose();
  });

  test('KIS live submit is disabled when validation is missing', () {
    final controller = _readyKisController();

    controller.orderValidationResult = null;

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Run a successful validation first.');
    controller.dispose();
  });

  test('KIS live submit is disabled when symbol changes after validation', () {
    final controller = _readyKisController()..setOrderTicketSymbol('000660');

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Run a successful validation first.');
    controller.dispose();
  });

  test('KIS live submit is disabled when qty changes after validation', () {
    final controller = _readyKisController()..setOrderTicketQty(2);

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Run a successful validation first.');
    controller.dispose();
  });

  test('KIS live submit is disabled when side changes after validation', () {
    final controller = _readyKisController()..setOrderTicketSide('sell');

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Run a successful validation first.');
    controller.dispose();
  });

  test('KIS live submit is disabled when runtime dry-run is ON', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(runtimeDryRun: true),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Live submit blocked: dry-run is ON');
    controller.dispose();
  });

  test('KIS live submit is disabled when kill switch is ON', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(killSwitch: true),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Live submit blocked: kill switch is ON');
    controller.dispose();
  });

  test('KIS live submit is disabled when KIS is disabled', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(kisEnabled: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Live submit blocked: KIS trading disabled');
    controller.dispose();
  });

  test('KIS live submit is disabled when real orders are disabled', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(kisRealOrderEnabled: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Live submit blocked: KIS real orders disabled');
    controller.dispose();
  });

  test('KIS live submit is disabled when market is closed', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(marketOpen: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Live submit blocked: market is closed');
    controller.dispose();
  });

  test('KIS live submit is disabled when entry is not allowed now', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(entryAllowedNow: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Live submit blocked: entry not allowed now (no_new_entry_after 15:00)');
    controller.dispose();
  });

  test('KIS live submit is enabled only when all checklist items pass', () {
    final controller = _readyKisController();

    expect(controller.canSubmitLiveKisOrder, isTrue);
    controller.dispose();
  });

  test('KR preview candidate can fill dry-run order ticket without validation',
      () {
    final api = _FakeApiClient(validationResult: _validationResult());
    final controller = DashboardController(api, autoload: false)
      ..selectedOrderMarket = PortfolioMarket.us
      ..orderTicketSymbol = 'AAPL'
      ..orderTicketSide = 'sell'
      ..orderTicketQty = 0
      ..orderValidationResult = _validationResult()
      ..orderValidationError = 'previous error';

    controller.useKrCandidateInOrderTicket(const Candidate(
      symbol: '005930',
      score: 64,
      note: 'preview',
      entryReady: false,
      actionHint: 'watch',
      blockReason: 'kr_trading_disabled',
    ));

    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'buy');
    expect(controller.orderTicketQty, 1);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(api.validationCalls, 0);

    controller.dispose();
  });

  test('KIS exit candidate prepares manual sell ticket without validation', () {
    final api = _FakeApiClient(validationResult: _validationResult());
    final controller = DashboardController(api, autoload: false)
      ..selectedOrderMarket = PortfolioMarket.us
      ..orderTicketSymbol = 'AAPL'
      ..orderTicketSide = 'buy'
      ..orderTicketQty = 9
      ..orderTicketQtyInput = '9'
      ..kisLiveConfirmation = true
      ..orderValidationResult = _validationResult()
      ..orderValidationError = 'previous error'
      ..kisManualOrderError = 'previous submit error';

    final result = controller.prepareKisManualSellFromExitCandidate(
      const KisLiveExitCandidate(
        symbol: '005930',
        side: 'sell',
        suggestedQuantity: 2,
        trigger: 'stop_loss',
        triggerSource: 'cost_basis_pl_pct',
        severity: 'review',
        actionHint: 'manual_confirm_sell',
        reason: 'Manual confirmation is required.',
        submitReady: false,
        manualConfirmRequired: true,
        realOrderSubmitAllowed: false,
        realOrderSubmitted: false,
        brokerSubmitCalled: false,
        manualSubmitCalled: false,
      ),
    );

    expect(result.success, isTrue);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.orderTicketQty, 2);
    expect(controller.orderTicketQtyInput, '2');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(controller.kisManualOrderError, isNull);
    expect(controller.hasExitPreflightPreparedSellTicket, isTrue);
    expect(controller.orderTicketSourceMetadata?['source'],
        'kis_live_exit_preflight');
    expect(controller.orderTicketSourceMetadata?['source_type'],
        'manual_confirm_exit');
    expect(controller.orderTicketSourceMetadata?['exit_trigger'], 'stop_loss');
    expect(controller.orderTicketSourceMetadata?['trigger_source'],
        'cost_basis_pl_pct');
    expect(controller.orderTicketSourceMetadata?['auto_sell_enabled'], isFalse);
    expect(api.validationCalls, 0);

    controller.dispose();
  });

  test('KIS position management prepares manual sell ticket read-only',
      () async {
    final api = _FakeApiClient(
      manualSellPreparation: const ManualSellPreparation(
        provider: 'kis',
        market: 'KR',
        symbol: '005930',
        companyName: 'Samsung Electronics',
        quantity: 2,
        currentPrice: 72000,
        estimatedAmount: 144000,
        exitReason: 'stop_loss_triggered',
        humanReason: 'Stop loss triggered',
        holdingStatus: 'SELL_READY',
        canPrepare: true,
        canSubmit: true,
        blockReasons: [],
        sourceMetadata: {'source': 'portfolio_position'},
        rawPayload: {'symbol': '005930'},
      ),
    );
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.alpaca
      ..selectedOrderMarket = PortfolioMarket.us
      ..orderTicketSymbol = 'AAPL'
      ..orderTicketSide = 'buy'
      ..orderTicketQty = 9
      ..orderTicketQtyInput = '9'
      ..kisLiveConfirmation = true
      ..orderValidationResult = _validationResult()
      ..orderValidationError = 'previous error'
      ..kisManualOrderError = 'previous submit error';

    final result = await controller.prepareKisManualSellFromManagedPosition(
      _managedPosition(),
    );

    expect(result.success, isTrue);
    expect(result.message,
        'Manual SELL ticket prepared. Open Trading to validate and submit.');
    expect(controller.selectedProvider, SelectedProvider.kis);
    expect(controller.selectedOrderMarket, PortfolioMarket.kr);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.orderTicketQty, 2);
    expect(controller.orderTicketQtyInput, '2');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);
    expect(controller.orderValidationError, isNull);
    expect(controller.kisManualOrderError, isNull);
    expect(controller.hasPreparedKisManualSellTicket, isTrue);
    expect(
        controller.orderTicketSourceMetadata?['source'], 'portfolio_position');
    expect(controller.orderTicketSourceMetadata?['source_type'],
        'operator_confirmed_position_exit');
    expect(controller.orderTicketSourceMetadata?['estimated_amount'], 144000);
    expect(api.prepareManualSellCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);

    controller.dispose();
  });

  test('KIS prepared manual sell validates through existing sell path',
      () async {
    final api = _FakeApiClient(
      manualSellPreparation: const ManualSellPreparation(
        provider: 'kis',
        market: 'KR',
        symbol: '005930',
        companyName: 'Samsung Electronics',
        quantity: 1,
        currentPrice: 72000,
        estimatedAmount: 72000,
        exitReason: 'operator_selected_position_exit',
        humanReason: 'Operator-selected position exit',
        holdingStatus: 'SELL_READY',
        canPrepare: true,
        canSubmit: true,
        blockReasons: [],
        sourceMetadata: {},
        rawPayload: {},
      ),
    );
    final controller = DashboardController(api, autoload: false);

    await controller.prepareKisManualSellFromManagedPosition(
      _managedPosition(quantity: 1),
    );
    final result = await controller.validateKisOrder();

    expect(result.success, isTrue);
    expect(api.validationCalls, 1);
    expect(api.lastValidationSide, 'sell');
    expect(controller.orderValidationResult?.side, 'sell');
    expect(api.submitCalls, 0);

    controller.dispose();
  });

  test('KIS auto readiness refresh stores blocked result', () async {
    final api = _FakeApiClient(autoReadiness: _autoReadiness());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshKisAutoReadiness();

    expect(result.success, isTrue);
    expect(api.fetchKisAutoReadinessCalls, 1);
    expect(controller.kisAutoReadinessLoaded, isTrue);
    expect(controller.kisAutoReadinessLoading, isFalse);
    expect(controller.kisAutoReadinessResult?.autoOrderReady, isFalse);
    expect(controller.kisAutoReadinessResult?.realOrderSubmitAllowed, isFalse);

    controller.dispose();
  });

  test('KIS auto preflight stores error and clears loading', () async {
    final api = _FakeApiClient(throwAutoPreflight: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisAutoPreflightOnce();

    expect(result.success, isFalse);
    expect(api.runKisAutoPreflightCalls, 1);
    expect(controller.kisAutoPreflightLoading, isFalse);
    expect(controller.kisAutoReadinessError, contains('preflight failed'));

    controller.dispose();
  });

  test('KIS shadow exit review refresh stores read-only result', () async {
    final api = _FakeApiClient(shadowExitReview: _shadowExitReview());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshKisShadowExitReview();

    expect(result.success, isTrue);
    expect(api.fetchKisShadowExitReviewCalls, 1);
    expect(controller.kisShadowExitReviewLoading, isFalse);
    expect(controller.latestKisShadowExitReview?.mode, 'shadow_exit_review');
    expect(controller.latestKisShadowExitReview?.safety.readOnly, isTrue);
    expect(controller.latestKisShadowExitReview?.safety.brokerSubmitCalled,
        isFalse);
    expect(api.validationCalls, 0);

    controller.dispose();
  });

  test('KIS shadow exit review refresh stores error and clears loading',
      () async {
    final api = _FakeApiClient(throwShadowExitReview: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshKisShadowExitReview();

    expect(result.success, isFalse);
    expect(api.fetchKisShadowExitReviewCalls, 1);
    expect(controller.kisShadowExitReviewLoading, isFalse);
    expect(controller.kisShadowExitReviewError, contains('review failed'));

    controller.dispose();
  });

  test('KIS shadow exit review queue refresh stores read-only queue', () async {
    final api = _FakeApiClient(shadowExitReviewQueue: _shadowExitReviewQueue());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshKisShadowExitReviewQueue();

    expect(result.success, isTrue);
    expect(api.fetchKisShadowExitReviewQueueCalls, 1);
    expect(controller.kisShadowExitReviewQueueLoading, isFalse);
    expect(controller.latestKisShadowExitReviewQueue?.mode,
        'shadow_exit_review_queue');
    expect(controller.latestKisShadowExitReviewQueue?.safety.readOnly, isTrue);
    expect(controller.latestKisShadowExitReviewQueue?.safety.brokerSubmitCalled,
        isFalse);
    expect(api.validationCalls, 0);

    controller.dispose();
  });

  test('KIS shadow exit review queue refresh stores error and clears loading',
      () async {
    final api = _FakeApiClient(throwShadowExitReviewQueue: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshKisShadowExitReviewQueue();

    expect(result.success, isFalse);
    expect(api.fetchKisShadowExitReviewQueueCalls, 1);
    expect(controller.kisShadowExitReviewQueueLoading, isFalse);
    expect(controller.kisShadowExitReviewQueueError, contains('queue failed'));

    controller.dispose();
  });

  test('KIS shadow exit queue mark-reviewed and dismiss refresh local state',
      () async {
    final api = _FakeApiClient(shadowExitReviewQueue: _shadowExitReviewQueue());
    final controller = DashboardController(api, autoload: false);

    final reviewed = await controller.markKisShadowExitQueueItemReviewed(
      '005930:take_profit:cost_basis_pl_pct',
      note: 'reviewed',
    );
    final dismissed = await controller.dismissKisShadowExitQueueItem(
      '005930:take_profit:cost_basis_pl_pct',
      note: 'dismissed',
    );

    expect(reviewed.success, isTrue);
    expect(dismissed.success, isTrue);
    expect(api.markKisShadowExitQueueItemReviewedCalls, 1);
    expect(api.dismissKisShadowExitQueueItemCalls, 1);
    expect(api.fetchKisShadowExitReviewQueueCalls, 2);
    expect(api.validationCalls, 0);
    expect(api.lastQueueNote, 'dismissed');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderValidationResult, isNull);

    controller.dispose();
  });

  test('KIS limited auto sell run stores guarded result without manual calls',
      () async {
    final api = _FakeApiClient(limitedAutoSell: _limitedAutoSell());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisLimitedAutoSellOnce();

    expect(result.success, isTrue);
    expect(api.runKisLimitedAutoSellCalls, 1);
    expect(controller.kisLimitedAutoSellLoading, isFalse);
    expect(controller.latestKisLimitedAutoSellResult?.mode,
        'kis_limited_auto_stop_loss_run');
    expect(
        controller.latestKisLimitedAutoSellResult?.realOrderSubmitted, isFalse);
    expect(
        controller.latestKisLimitedAutoSellResult?.manualSubmitCalled, isFalse);
    expect(api.validationCalls, 0);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });

  test('KIS limited auto sell run stores error and clears loading', () async {
    final api = _FakeApiClient(throwLimitedAutoSell: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisLimitedAutoSellOnce();

    expect(result.success, isFalse);
    expect(api.runKisLimitedAutoSellCalls, 1);
    expect(controller.kisLimitedAutoSellLoading, isFalse);
    expect(controller.kisLimitedAutoSellError, contains('limited failed'));

    controller.dispose();
  });

  test('KIS buy shadow run stores result without manual calls', () async {
    final api = _FakeApiClient(buyShadow: _buyShadow());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisBuyShadowOnce();

    expect(result.success, isTrue);
    expect(api.runKisBuyShadowCalls, 1);
    expect(controller.kisBuyShadowLoading, isFalse);
    expect(controller.latestKisBuyShadowDecision?.mode, 'shadow_buy_dry_run');
    expect(controller.latestKisBuyShadowDecision?.realOrderSubmitted, isFalse);
    expect(controller.latestKisBuyShadowDecision?.manualSubmitCalled, isFalse);
    expect(api.validationCalls, 0);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });

  test('KIS buy shadow run stores error and clears loading', () async {
    final api = _FakeApiClient(throwBuyShadow: true);
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisBuyShadowOnce();

    expect(result.success, isFalse);
    expect(api.runKisBuyShadowCalls, 1);
    expect(controller.kisBuyShadowLoading, isFalse);
    expect(controller.kisBuyShadowError, contains('buy shadow failed'));

    controller.dispose();
  });

  test('KIS limited auto buy run stores guarded result without manual calls',
      () async {
    final api = _FakeApiClient(limitedAutoBuy: _limitedAutoBuy());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisLimitedAutoBuyOnce();

    expect(result.success, isTrue);
    expect(api.runKisLimitedAutoBuyCalls, 1);
    expect(controller.kisLimitedAutoBuyLoading, isFalse);
    expect(controller.latestKisLimitedAutoBuyResult?.mode,
        'kis_limited_auto_buy_run');
    expect(
        controller.latestKisLimitedAutoBuyResult?.realOrderSubmitted, isFalse);
    expect(
        controller.latestKisLimitedAutoBuyResult?.manualSubmitCalled, isFalse);
    expect(api.validationCalls, 0);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });

  test(
      'KIS single-symbol Analyze & Buy passes selected symbol and confirm flag',
      () async {
    final api = _FakeApiClient(kisSingle: _kisSingleResult());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisSingleSymbolAnalyzeBuy(
      symbol: '005380',
      quantity: 2,
      gateLevel: 4,
      confirmLive: true,
    );

    expect(result.success, isTrue);
    expect(api.runKisSingleCalls, 1);
    expect(api.lastKisSingleSymbol, '005380');
    expect(api.lastKisSingleQuantity, 2);
    expect(api.lastKisSingleGateLevel, 4);
    expect(api.lastKisSingleConfirmLive, isTrue);
    expect(controller.kisSingleSymbolTradingLoading, isFalse);
    expect(controller.latestKisSingleSymbolTradingResult?.requestedSymbol,
        '005380');
    expect(controller.latestKisSingleSymbolTradingResult?.realOrderSubmitted,
        isFalse);

    controller.dispose();
  });

  test('KIS scheduler live run stores guarded result without manual calls',
      () async {
    final api = _FakeApiClient(schedulerLive: _schedulerLive());
    final controller = DashboardController(api, autoload: false);

    final result = await controller.runKisSchedulerLiveOnce();

    expect(result.success, isTrue);
    expect(api.runKisSchedulerLiveCalls, 1);
    expect(controller.kisSchedulerLiveLoading, isFalse);
    expect(controller.latestKisSchedulerLiveResult?.mode,
        'kis_scheduler_live_once');
    expect(
        controller.latestKisSchedulerLiveResult?.realOrderSubmitted, isFalse);
    expect(
        controller.latestKisSchedulerLiveResult?.manualSubmitCalled, isFalse);
    expect(api.validationCalls, 0);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });
}

DashboardController _readyKisController({
  KisManualOrderSafetyStatus? safetyStatus,
}) {
  final validation = _validationResult();
  return DashboardController(
    _FakeApiClient(safetyStatus: safetyStatus ?? _safetyStatus()),
    autoload: false,
  )
    ..selectOrderMarket(PortfolioMarket.kr)
    ..setOrderTicketSymbol(validation.symbol)
    ..setOrderTicketSide(validation.side)
    ..setOrderTicketQty(validation.qty)
    ..orderValidationResult = validation
    ..kisLiveConfirmation = true
    ..kisSafetyStatus = safetyStatus ?? _safetyStatus();
}

KisManualOrderSafetyStatus _safetyStatus({
  bool runtimeDryRun = false,
  bool killSwitch = false,
  bool kisEnabled = true,
  bool kisRealOrderEnabled = true,
  bool marketOpen = true,
  bool entryAllowedNow = true,
}) {
  return KisManualOrderSafetyStatus(
    runtimeDryRun: runtimeDryRun,
    killSwitch: killSwitch,
    kisEnabled: kisEnabled,
    kisRealOrderEnabled: kisRealOrderEnabled,
    marketOpen: marketOpen,
    entryAllowedNow: entryAllowedNow,
    noNewEntryAfter: '15:00',
  );
}

ManagedPosition _managedPosition({
  String symbol = '005930',
  double quantity = 2,
  String holdingStatus = 'SELL_READY',
  bool stopLossTriggered = true,
  bool takeProfitTriggered = false,
  bool manualReviewRequired = true,
}) {
  return ManagedPosition(
    provider: 'kis',
    market: 'KR',
    symbol: symbol,
    companyName: 'Samsung Electronics',
    quantity: quantity,
    averagePrice: 70000,
    costBasis: 140000,
    currentPrice: 72000,
    currentValue: 144000,
    unrealizedPl: 4000,
    unrealizedPlPct: 0.028,
    holdingStatus: holdingStatus,
    exitReason: 'stop_loss_triggered',
    humanReason: 'Stop loss triggered',
    stopLossTriggered: stopLossTriggered,
    takeProfitTriggered: takeProfitTriggered,
    weakTrendTriggered: false,
    sellPressureTriggered: false,
    manualReviewRequired: manualReviewRequired,
    finalSellScore: 80,
    finalBuyScore: 20,
    quantSellScore: 78,
    quantBuyScore: 18,
    aiSellScore: 82,
    aiBuyScore: 22,
    confidence: 0.9,
    technicalSnapshot: const {},
    riskFlags: const [],
    gatingNotes: const [],
    blockReasons: const [],
    canPrepareManualSell: true,
    canSubmitManualSell: true,
    latestManualSellOrder: null,
    rawPayload: const {},
  );
}

KisAutoReadiness _autoReadiness({bool preflight = false}) {
  return KisAutoReadiness.fromJson({
    'auto_order_ready': false,
    'future_auto_order_ready': false,
    'live_auto_enabled': false,
    'real_order_submit_allowed': false,
    'reason': 'live_auto_disabled_by_default',
    'preflight': preflight,
    'checks': {
      'dry_run': true,
      'kill_switch': false,
      'live_auto_buy_enabled': false,
      'live_auto_sell_enabled': false,
    },
    'safety': {
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'scheduler_real_order_enabled': false,
      'requires_manual_confirm': true,
    },
  });
}

KisShadowExitReview _shadowExitReview() {
  return KisShadowExitReview.fromJson({
    'status': 'ok',
    'mode': 'shadow_exit_review',
    'review_window_days': 30,
    'summary': {
      'total_shadow_runs': 1,
      'would_sell_count': 1,
      'hold_count': 0,
      'manual_review_count': 0,
      'no_submit_invariant_ok': true,
    },
    'recent_decisions': const [],
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
      'no_submit_invariant_ok': true,
    },
  });
}

KisShadowExitReviewQueue _shadowExitReviewQueue() {
  return KisShadowExitReviewQueue.fromJson({
    'status': 'ok',
    'mode': 'shadow_exit_review_queue',
    'review_window_days': 30,
    'summary': {
      'open_count': 1,
      'reviewed_count': 0,
      'dismissed_count': 0,
      'would_sell_open_count': 1,
      'manual_review_open_count': 0,
      'repeated_symbol_count': 1,
      'latest_open_at': '2026-05-15T01:03:00+00:00',
    },
    'items': [
      {
        'queue_id': '005930:take_profit:cost_basis_pl_pct',
        'symbol': '005930',
        'decision': 'would_sell',
        'action': 'sell',
        'trigger': 'take_profit',
        'trigger_source': 'cost_basis_pl_pct',
        'severity': 'review',
        'occurrence_count': 2,
        'latest_unrealized_pl': 2500,
        'latest_unrealized_pl_pct': 0.031,
        'status': 'open',
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }
    ],
    'safety': {
      'read_only': true,
      'operator_state_only': true,
      'creates_orders': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    },
  });
}

KisLimitedAutoSell _limitedAutoSell() {
  return KisLimitedAutoSell.fromJson({
    'status': 'ok',
    'mode': 'kis_limited_auto_stop_loss_run',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'dry_run_true',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'live_auto_sell_enabled': false,
    'stop_loss_auto_sell_enabled': false,
    'take_profit_auto_sell_enabled': false,
    'scheduler_real_orders_enabled': false,
    'dry_run': true,
    'kill_switch': false,
    'block_reasons': ['dry_run_true'],
    'checks': {'kis_limited_auto_stop_loss_enabled': false},
    'safety': {
      'max_orders_per_day': 1,
      'stop_loss_only': true,
      'take_profit_auto_sell_enabled': false,
    },
  });
}

KisBuyShadowDecision _buyShadow() {
  return KisBuyShadowDecision.fromJson({
    'status': 'ok',
    'mode': 'shadow_buy_dry_run',
    'decision': 'would_buy',
    'action': 'buy',
    'reason': 'Shadow buy candidate only. No broker submit.',
    'symbol': '005930',
    'candidate': {
      'symbol': '005930',
      'final_score': 82.5,
      'confidence': 0.76,
      'quant_score': 78,
      'gpt_buy_score': 65,
      'current_price': 72000,
      'suggested_notional': 288000,
      'suggested_quantity': 4,
      'risk_flags': ['shadow_buy_only'],
      'gating_notes': ['no_broker_submit'],
      'audit_metadata': {'source': 'kis_buy_shadow_decision'},
    },
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'auto_buy_enabled': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'checks': {'kis_limited_auto_buy_shadow_enabled': true},
    'safety': {'read_only': true},
  });
}

KisLimitedAutoBuy _limitedAutoBuy({String mode = 'kis_limited_auto_buy_run'}) {
  return KisLimitedAutoBuy.fromJson({
    'status': 'ok',
    'mode': mode,
    'source': 'kis_limited_auto_buy',
    'source_type': 'buy_readiness_only',
    'result': 'readiness_only',
    'action': 'buy_ready',
    'reason': 'buy_readiness_only',
    'primary_block_reason': 'auto_buy_execution_disabled',
    'symbol': '005930',
    'quantity': 4,
    'estimated_notional': 288000,
    'final_buy_score': 82.5,
    'final_sell_score': 12,
    'confidence': 0.76,
    'required_buy_score': 75,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'auto_buy_enabled': false,
    'live_auto_buy_enabled': false,
    'limited_auto_buy_enabled': false,
    'buy_readiness_enabled': true,
    'scheduler_real_orders_enabled': false,
    'block_reasons': ['auto_buy_execution_disabled'],
    'final_candidate': _limitedAutoBuyCandidate(),
    'candidates': [_limitedAutoBuyCandidate()],
    'checks': {'kis_limited_auto_buy_enabled': false},
    'safety': {'buy_readiness_only': true, 'max_orders_per_day': 1},
  });
}

Map<String, dynamic> _limitedAutoBuyCandidate() {
  return {
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'status': 'BUY READY',
    'current_price': 72000,
    'available_cash': 3000000,
    'estimated_notional': 288000,
    'suggested_quantity': 4,
    'final_buy_score': 82.5,
    'final_sell_score': 12,
    'confidence': 0.76,
    'required_buy_score': 75,
    'buy_sell_spread': 70.5,
    'entry_ready': true,
    'trade_allowed': false,
    'buy_readiness_only': true,
    'buy_actionable': false,
    'cash_sufficient': true,
    'market_session_allowed': true,
    'block_reasons': [],
    'technical_snapshot': {'EMA20': 70500, 'RSI': 57.5},
  };
}

KisSingleSymbolTradingResult _kisSingleResult({String symbol = '005380'}) {
  return KisSingleSymbolTradingResult.fromJson({
    'status': 'ok',
    'mode': 'kis_single_symbol_analyze_buy',
    'provider': 'kis',
    'market': 'KR',
    'symbol': symbol,
    'requested_symbol': symbol,
    'analyzed_symbol': symbol,
    'symbol_match': true,
    'result': 'dry_run',
    'action': 'buy',
    'reason': 'dry_run_mode',
    'quantity': 1,
    'primary_score': 82,
    'final_buy_score': 82,
    'final_sell_score': 9,
    'confidence': 0.8,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'dry_run': true,
    'safety': {'dry_run': true},
  });
}

KisSchedulerLiveResult _schedulerLive() {
  return KisSchedulerLiveResult.fromJson({
    'status': 'ok',
    'mode': 'kis_scheduler_live_once',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'kis_scheduler_live_disabled',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'scheduler_real_order_enabled': false,
    'checks': {'kis_scheduler_live_enabled': false},
    'safety': {'max_live_orders_per_day': 2},
  });
}

Map<String, dynamic> _queueActionJson({required String status, String? note}) {
  return {
    'status': 'ok',
    'mode': 'shadow_exit_review_queue',
    'action': status == 'reviewed' ? 'mark-reviewed' : 'dismiss',
    'item': {
      'queue_id': '005930:take_profit:cost_basis_pl_pct',
      'symbol': '005930',
      'trigger': 'take_profit',
      'status': status,
      'operator_note': note,
    },
    'safety': {
      'read_only': true,
      'operator_state_only': true,
      'creates_orders': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    },
  };
}

class _FakeApiClient extends ApiClient {
  _FakeApiClient({
    this.latest,
    this.throwLatest = false,
    this.usPortfolio,
    this.krPortfolio,
    this.throwKrPortfolio = false,
    this.usWatchlist,
    this.krWatchlist,
    this.validationResult,
    this.safetyStatus,
    this.settingsDryRun = true,
    this.refreshedDryRun,
    this.throwUpdateOpsSettings = false,
    this.autoReadiness,
    this.throwAutoPreflight = false,
    this.shadowExitReview,
    this.throwShadowExitReview = false,
    this.shadowExitReviewQueue,
    this.throwShadowExitReviewQueue = false,
    this.limitedAutoSell,
    this.throwLimitedAutoSell = false,
    this.buyShadow,
    this.throwBuyShadow = false,
    this.limitedAutoBuy,
    this.kisSingle,
    this.schedulerLive,
    this.recentRuns = const [],
    this.throwRecentOrders = false,
    this.guardedSell,
    this.guardedBuy,
    this.managedPositions = const [],
    this.updatedKosdaqWatchlist,
    this.manualSellPreparation,
  });

  final WatchlistRunResult? latest;
  final bool throwLatest;
  final PortfolioSummary? usPortfolio;
  final PortfolioSummary? krPortfolio;
  final bool throwKrPortfolio;
  final MarketWatchlist? usWatchlist;
  final MarketWatchlist? krWatchlist;
  final OrderValidationResult? validationResult;
  final KisManualOrderSafetyStatus? safetyStatus;
  final bool settingsDryRun;
  final bool? refreshedDryRun;
  final bool throwUpdateOpsSettings;
  final KisAutoReadiness? autoReadiness;
  final bool throwAutoPreflight;
  final KisShadowExitReview? shadowExitReview;
  final bool throwShadowExitReview;
  final KisShadowExitReviewQueue? shadowExitReviewQueue;
  final bool throwShadowExitReviewQueue;
  final KisLimitedAutoSell? limitedAutoSell;
  final bool throwLimitedAutoSell;
  final KisBuyShadowDecision? buyShadow;
  final bool throwBuyShadow;
  final KisLimitedAutoBuy? limitedAutoBuy;
  final KisSingleSymbolTradingResult? kisSingle;
  final KisSchedulerLiveResult? schedulerLive;
  final List<TradingLogItem> recentRuns;
  final bool throwRecentOrders;
  final KisSchedulerGuardedSellResult? guardedSell;
  final KisSchedulerGuardedBuyResult? guardedBuy;
  final List<ManagedPosition> managedPositions;
  final MarketWatchlist? updatedKosdaqWatchlist;
  final ManualSellPreparation? manualSellPreparation;
  int mockCalls = 0;
  int getOpsSettingsCalls = 0;
  int updateOpsSettingsCalls = 0;
  int fetchKisAutoReadinessCalls = 0;
  int runKisAutoPreflightCalls = 0;
  int fetchKisShadowExitReviewCalls = 0;
  int fetchKisShadowExitReviewQueueCalls = 0;
  int markKisShadowExitQueueItemReviewedCalls = 0;
  int dismissKisShadowExitQueueItemCalls = 0;
  int runKisLimitedAutoSellCalls = 0;
  int runKisBuyShadowCalls = 0;
  int fetchKisLimitedAutoBuyStatusCalls = 0;
  int runKisLimitedAutoBuyPreflightCalls = 0;
  int runKisLimitedAutoBuyCalls = 0;
  int runKisSingleCalls = 0;
  int runKisSchedulerLiveCalls = 0;
  int fetchRecentRunsCalls = 0;
  int fetchRecentOrdersCalls = 0;
  int fetchRecentSignalsCalls = 0;
  int fetchKisGuardedSellStatusCalls = 0;
  int fetchKisGuardedBuyStatusCalls = 0;
  int updateKosdaqTop50WatchlistCalls = 0;
  int prepareManualSellCalls = 0;
  int submitCalls = 0;
  String? lastQueueNote;
  Map<String, dynamic>? lastSettingsUpdate;
  int validationCalls = 0;
  String? lastValidationSide;
  String? lastProvider;
  int? lastGateLevel;
  int? lastKisGateLevel;
  String? lastKisSingleSymbol;
  int? lastKisSingleGateLevel;
  int? lastKisSingleQuantity;
  bool? lastKisSingleConfirmLive;

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    final override = safetyStatus;
    final runtimeDryRun = override?.runtimeDryRun ??
        (getOpsSettingsCalls > 1
            ? (refreshedDryRun ?? settingsDryRun)
            : settingsDryRun);
    return KisManualOrderSafetyStatus(
      runtimeDryRun: runtimeDryRun,
      killSwitch: override?.killSwitch ?? false,
      kisEnabled: override?.kisEnabled ?? true,
      kisRealOrderEnabled: override?.kisRealOrderEnabled ?? true,
      marketOpen: override?.marketOpen ?? true,
      entryAllowedNow: override?.entryAllowedNow ?? true,
      noNewEntryAfter: override?.noNewEntryAfter ?? '15:00',
    );
  }

  @override
  Future<OpsSettings> getOpsSettings() async {
    getOpsSettingsCalls += 1;
    return OpsSettings(
      schedulerEnabled: false,
      botEnabled: false,
      dryRun: getOpsSettingsCalls > 1
          ? (refreshedDryRun ?? settingsDryRun)
          : settingsDryRun,
      killSwitch: false,
      brokerMode: 'Paper',
      defaultGateLevel: 2,
      maxDailyTrades: 5,
      maxDailyEntries: 2,
      minEntryScore: 65,
      minScoreGap: 3,
    );
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    updateOpsSettingsCalls += 1;
    lastSettingsUpdate = values;
    if (throwUpdateOpsSettings) {
      throw const ApiRequestException(
          'HTTP 500: {"message":"settings failed"}');
    }
  }

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async => const SchedulerStatus(
        runtimeSchedulerEnabled: true,
        us: MarketSchedulerStatus(
          enabledForScheduler: true,
          timezone: 'America/New_York',
          slots: [],
        ),
        kr: MarketSchedulerStatus(
          enabledForScheduler: true,
          timezone: 'Asia/Seoul',
          slots: [],
          previewOnly: true,
          realOrdersAllowed: false,
        ),
      );

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

  @override
  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    fetchRecentRunsCalls += 1;
    return recentRuns;
  }

  @override
  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    fetchRecentOrdersCalls += 1;
    if (throwRecentOrders) {
      throw const ApiRequestException('orders unavailable');
    }
    return const [];
  }

  @override
  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    fetchRecentSignalsCalls += 1;
    return const [];
  }

  @override
  Future<KisSchedulerGuardedSellResult>
      fetchKisSchedulerGuardedSellStatus() async {
    fetchKisGuardedSellStatusCalls += 1;
    return guardedSell ?? _guardedSellStatus();
  }

  @override
  Future<KisSchedulerGuardedBuyResult>
      fetchKisSchedulerGuardedBuyStatus() async {
    fetchKisGuardedBuyStatusCalls += 1;
    return guardedBuy ?? _guardedBuyStatus();
  }

  @override
  Future<KisAutoReadiness> fetchKisAutoReadiness() async {
    fetchKisAutoReadinessCalls += 1;
    return autoReadiness ?? _autoReadiness();
  }

  @override
  Future<KisAutoReadiness> runKisAutoPreflightOnce() async {
    runKisAutoPreflightCalls += 1;
    if (throwAutoPreflight) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"preflight failed"}',
      );
    }
    return autoReadiness ?? _autoReadiness(preflight: true);
  }

  @override
  Future<KisShadowExitReview> fetchKisShadowExitReview({
    int days = 30,
    int limit = 20,
    String? symbol,
  }) async {
    fetchKisShadowExitReviewCalls += 1;
    if (throwShadowExitReview) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"review failed"}',
      );
    }
    return shadowExitReview ?? _shadowExitReview();
  }

  @override
  Future<KisShadowExitReviewQueue> fetchKisShadowExitReviewQueue({
    int days = 30,
    int limit = 50,
  }) async {
    fetchKisShadowExitReviewQueueCalls += 1;
    if (throwShadowExitReviewQueue) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"queue failed"}',
      );
    }
    return shadowExitReviewQueue ?? _shadowExitReviewQueue();
  }

  @override
  Future<KisShadowExitReviewQueueAction> markKisShadowExitQueueItemReviewed(
    String queueId, {
    String? note,
  }) async {
    markKisShadowExitQueueItemReviewedCalls += 1;
    lastQueueNote = note;
    return KisShadowExitReviewQueueAction.fromJson(_queueActionJson(
      status: 'reviewed',
      note: note,
    ));
  }

  @override
  Future<KisShadowExitReviewQueueAction> dismissKisShadowExitQueueItem(
    String queueId, {
    String? note,
  }) async {
    dismissKisShadowExitQueueItemCalls += 1;
    lastQueueNote = note;
    return KisShadowExitReviewQueueAction.fromJson(_queueActionJson(
      status: 'dismissed',
      note: note,
    ));
  }

  @override
  Future<KisLimitedAutoSell> runKisLimitedAutoSellOnce() async {
    runKisLimitedAutoSellCalls += 1;
    if (throwLimitedAutoSell) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"limited failed"}',
      );
    }
    return limitedAutoSell ?? _limitedAutoSell();
  }

  @override
  Future<KisBuyShadowDecision> runKisBuyShadowOnce() async {
    runKisBuyShadowCalls += 1;
    if (throwBuyShadow) {
      throw const ApiRequestException(
        'HTTP 503: {"message":"buy shadow failed"}',
      );
    }
    return buyShadow ?? _buyShadow();
  }

  @override
  Future<KisLimitedAutoBuy> fetchKisLimitedAutoBuyStatus(
      {int? gateLevel}) async {
    fetchKisLimitedAutoBuyStatusCalls += 1;
    return limitedAutoBuy ??
        _limitedAutoBuy(mode: 'kis_limited_auto_buy_status');
  }

  @override
  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyPreflightOnce({
    int? gateLevel,
  }) async {
    runKisLimitedAutoBuyPreflightCalls += 1;
    return limitedAutoBuy ??
        _limitedAutoBuy(mode: 'kis_limited_auto_buy_preflight');
  }

  @override
  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyOnce({int? gateLevel}) async {
    runKisLimitedAutoBuyCalls += 1;
    return limitedAutoBuy ?? _limitedAutoBuy();
  }

  @override
  Future<KisSingleSymbolTradingResult> runKisSingleSymbolAnalyzeBuy({
    required String symbol,
    int? gateLevel,
    int? quantity,
    double? amount,
    required bool confirmLive,
  }) async {
    runKisSingleCalls += 1;
    lastKisSingleSymbol = symbol;
    lastKisSingleGateLevel = gateLevel;
    lastKisSingleQuantity = quantity;
    lastKisSingleConfirmLive = confirmLive;
    return kisSingle ?? _kisSingleResult(symbol: symbol);
  }

  @override
  Future<KisSchedulerLiveResult> runKisSchedulerLiveOnce() async {
    runKisSchedulerLiveCalls += 1;
    return schedulerLive ?? _schedulerLive();
  }

  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async =>
      usPortfolio ?? PortfolioSummary.empty();

  @override
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
  }

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async {
    if (throwKrPortfolio) {
      throw const ApiRequestException('KIS unavailable');
    }
    return krPortfolio ?? PortfolioSummary.empty(currency: 'KRW');
  }

  @override
  Future<List<ManagedPosition>> fetchKisManagedPositions() async {
    return managedPositions;
  }

  @override
  Future<MarketWatchlist> fetchMarketWatchlist(String market) async {
    if (market.toUpperCase() == 'KR') {
      if (updateKosdaqTop50WatchlistCalls > 0 &&
          updatedKosdaqWatchlist != null) {
        return updatedKosdaqWatchlist!;
      }
      return krWatchlist ?? MarketWatchlist.empty('KR');
    }
    return usWatchlist ?? MarketWatchlist.empty('US');
  }

  @override
  Future<Map<String, dynamic>> updateKosdaqTop50Watchlist() async {
    updateKosdaqTop50WatchlistCalls += 1;
    return {
      'provider': 'kis',
      'market': 'KR',
      'source_market': 'KR',
      'source_market_label': '한국',
      'group_label': '코스피 Top 30 + 코스닥 Top 20',
      'mode': 'kr_watchlist_balanced_update_applied',
      'updated': true,
      'count': 50,
      'target_count': 50,
      'groups': [
        {
          'market': 'KOSPI',
          'market_label': '코스피',
          'target_count': 30,
          'count': 30,
        },
        {
          'market': 'KOSDAQ',
          'market_label': '코스닥',
          'target_count': 20,
          'count': 20,
        },
      ],
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    };
  }

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    Map<String, dynamic>? sourceMetadata,
  }) async {
    validationCalls += 1;
    lastValidationSide = side;
    return validationResult ??
        _validationResult(symbol: symbol, side: side, qty: qty);
  }

  @override
  Future<ManualSellPreparation> prepareKisManualSell(String symbol) async {
    prepareManualSellCalls += 1;
    return manualSellPreparation ??
        ManualSellPreparation(
          provider: 'kis',
          market: 'KR',
          symbol: symbol,
          companyName: 'Samsung Electronics',
          quantity: 1,
          currentPrice: 72000,
          estimatedAmount: 72000,
          exitReason: 'operator_selected_position_exit',
          humanReason: 'Operator-selected position exit',
          holdingStatus: 'SELL_READY',
          canPrepare: true,
          canSubmit: true,
          blockReasons: const [],
          sourceMetadata: const {},
          rawPayload: const {},
        );
  }

  @override
  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    submitCalls += 1;
    return KisManualOrderResult.fromJson({
      'order_id': 1,
      'symbol': symbol,
      'side': side,
      'qty': qty,
      'internal_status': 'SUBMITTED',
      'created_at': '2026-05-17T00:00:00',
      'updated_at': '2026-05-17T00:00:00',
    });
  }

  @override
  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async {
    if (throwLatest) {
      throw const ApiRequestException('offline');
    }
    return latest;
  }

  @override
  Future<WatchlistRunResult> runKisWatchlistPreview({
    int gateLevel = 2,
  }) async {
    lastKisGateLevel = gateLevel;
    return latest ?? _resultFor('KIS');
  }

  @override
  Future<WatchlistRunResult> runWatchlistForProvider({
    required String provider,
    required int gateLevel,
  }) async {
    lastProvider = provider;
    lastGateLevel = gateLevel;

    if (provider.trim().toLowerCase() == 'kis') {
      return runKisWatchlistPreview(gateLevel: gateLevel);
    }

    return runWatchlistOnce();
  }

  @override
  Future<WatchlistRunResult> runWatchlistOnce() async =>
      latest ?? _resultFor('US');

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  WatchlistRunResult getMockRunResult() {
    mockCalls += 1;
    return _resultFor('MOCK');
  }
}

MarketWatchlist _watchlist(String market, List<String> symbols) {
  return MarketWatchlist(
    market: market,
    currency: market == 'KR' ? 'KRW' : 'USD',
    timezone: market == 'KR' ? 'Asia/Seoul' : 'America/New_York',
    watchlistFile: 'config/watchlist_${market.toLowerCase()}.yaml',
    count: symbols.length,
    symbols: [
      for (final symbol in symbols)
        WatchlistSymbol(symbol: symbol, name: '', market: market),
    ],
  );
}

OrderValidationResult _validationResult({
  String symbol = '005930',
  String side = 'buy',
  int qty = 1,
}) {
  return OrderValidationResult(
    provider: 'kis',
    market: 'KR',
    environment: 'prod',
    dryRun: true,
    validatedForSubmission: true,
    canSubmitLater: true,
    symbol: symbol,
    side: side,
    qty: qty,
    orderType: 'market',
    currentPrice: 72000,
    estimatedAmount: 72000,
    availableCash: 1000000,
    heldQty: null,
    warnings: const [],
    blockReasons: const [],
    marketSession: const MarketSessionStatus(
      market: 'KR',
      timezone: 'Asia/Seoul',
      isMarketOpen: true,
      isEntryAllowedNow: true,
      isNearClose: false,
    ),
    orderPreview: const OrderPreview(
      accountNoMasked: '12****78',
      productCode: '01',
      symbol: '005930',
      side: 'buy',
      qty: 1,
      orderType: 'market',
      kisTrIdPreview: 'TTTC0802U',
      payloadPreview: {'CANO': '12****78', 'PDNO': '005930'},
    ),
  );
}

PortfolioSummary _portfolio(String currency, {required double marketValue}) {
  return PortfolioSummary(
    currency: currency,
    positionsCount: 0,
    pendingOrdersCount: 0,
    totalCostBasis: 0,
    totalMarketValue: marketValue,
    totalUnrealizedPl: 0,
    totalUnrealizedPlpc: 0,
    cash: 0,
    positions: const [],
    pendingOrders: const [],
  );
}

WatchlistRunResult _resultFor(String symbol) {
  return WatchlistRunResult(
    configuredSymbolCount: 50,
    analyzedSymbolCount: 50,
    quantCandidatesCount: 1,
    researchedCandidatesCount: 1,
    finalBestCandidate: symbol,
    secondFinalCandidate: 'MSFT',
    tiedFinalCandidates: const [],
    nearTiedCandidates: const [],
    tieBreakerApplied: false,
    finalCandidateSelectionReason: '$symbol selected',
    bestScore: 72,
    finalScoreGap: 8,
    minEntryScore: 65,
    minScoreGap: 3,
    shouldTrade: false,
    triggeredSymbol: null,
    triggerBlockReason: 'weak_final_score_gap',
    finalEntryReady: false,
    finalActionHint: 'watch',
    action: 'hold',
    orderId: null,
    topQuantCandidates: const [],
    researchedCandidates: const [],
    finalRankedCandidates: const [],
    result: 'skipped',
    reason: 'weak_final_score_gap',
    triggerSource: 'manual',
  );
}

TradingLogItem _alpacaSchedulerRun() {
  return const TradingLogItem(
    id: 100,
    runKey: 'alpaca-scheduler',
    provider: 'alpaca',
    market: 'US',
    symbol: 'AAPL',
    triggerSource: 'scheduler',
    mode: 'watchlist_run',
    action: 'hold',
    result: 'skipped',
    reason: 'weak_final_score_gap',
    relatedOrderId: null,
    createdAt: '2026-05-28T01:00:00Z',
    gateLevel: 2,
  );
}

KisSchedulerGuardedSellResult _guardedSellStatus() {
  return KisSchedulerGuardedSellResult.fromJson({
    'status': 'ok',
    'result': 'blocked',
    'action': 'sell',
    'reason': 'market_closed',
    'primary_block_reason': 'market_closed',
    'trigger': 'take_profit',
    'symbol': '005930',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'daily_limit': {
      'today_submitted_count': 0,
      'max_live_orders_per_day': 2,
      'remaining': 2,
    },
    'created_at': '2026-05-28T02:30:00Z',
  });
}

KisSchedulerGuardedBuyResult _guardedBuyStatus() {
  return KisSchedulerGuardedBuyResult.fromJson({
    'status': 'ok',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'scheduler_buy_disabled',
    'primary_block_reason': 'scheduler_buy_disabled',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'created_at': '2026-05-28T02:31:00Z',
  });
}
