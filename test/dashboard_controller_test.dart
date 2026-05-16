import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:auto_invest_dashboard/models/kis_auto_readiness.dart';
import 'package:auto_invest_dashboard/models/kis_live_exit_preflight.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/kis_shadow_exit_review.dart';
import 'package:auto_invest_dashboard/models/kis_shadow_exit_review_queue.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
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
        'Current order input changed after validation. Validate again.');
    controller.dispose();
  });

  test('KIS live submit is disabled when qty changes after validation', () {
    final controller = _readyKisController()..setOrderTicketQty(2);

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Current order input changed after validation. Validate again.');
    controller.dispose();
  });

  test('KIS live submit is disabled when side changes after validation', () {
    final controller = _readyKisController()..setOrderTicketSide('sell');

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Current order input changed after validation. Validate again.');
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
  int mockCalls = 0;
  int getOpsSettingsCalls = 0;
  int updateOpsSettingsCalls = 0;
  int fetchKisAutoReadinessCalls = 0;
  int runKisAutoPreflightCalls = 0;
  int fetchKisShadowExitReviewCalls = 0;
  int fetchKisShadowExitReviewQueueCalls = 0;
  int markKisShadowExitQueueItemReviewedCalls = 0;
  int dismissKisShadowExitQueueItemCalls = 0;
  String? lastQueueNote;
  Map<String, dynamic>? lastSettingsUpdate;
  int validationCalls = 0;
  String? lastProvider;
  int? lastGateLevel;
  int? lastKisGateLevel;

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
  Future<SchedulerStatus> fetchSchedulerStatus() async =>
      SchedulerStatus.safeDefault();

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

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
  Future<MarketWatchlist> fetchMarketWatchlist(String market) async {
    if (market.toUpperCase() == 'KR') {
      return krWatchlist ?? MarketWatchlist.empty('KR');
    }
    return usWatchlist ?? MarketWatchlist.empty('US');
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
    return validationResult ??
        _validationResult(symbol: symbol, side: side, qty: qty);
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
