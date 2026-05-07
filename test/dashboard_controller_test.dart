import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/candidate.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
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
    final api = _FakeApiClient(settingsDryRun: true, throwUpdateOpsSettings: true);
    final controller = DashboardController(api, autoload: false);

    await controller.load();
    final result = await controller.setDryRun(false);

    expect(result.success, isFalse);
    expect(api.updateOpsSettingsCalls, 1);
    expect(controller.settings.dryRun, isTrue);
    expect(controller.dryRunLoading, isFalse);

    controller.dispose();
  });


  test('KIS live submit is disabled when validation is missing', () {
    final controller = _readyKisController();

    controller.orderValidationResult = null;

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(), 'Run a successful validation first.');
    controller.dispose();
  });

  test('KIS live submit is disabled when symbol changes after validation', () {
    final controller = _readyKisController()
      ..setOrderTicketSymbol('000660');

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Current order input changed after validation. Validate again.');
    controller.dispose();
  });

  test('KIS live submit is disabled when qty changes after validation', () {
    final controller = _readyKisController()
      ..setOrderTicketQty(2);

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Current order input changed after validation. Validate again.');
    controller.dispose();
  });

  test('KIS live submit is disabled when side changes after validation', () {
    final controller = _readyKisController()
      ..setOrderTicketSide('sell');

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
    expect(controller.kisSubmitBlockedMessage(), 'Backend dry-run is ON.');
    controller.dispose();
  });

  test('KIS live submit is disabled when kill switch is ON', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(killSwitch: true),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(), 'Kill switch is ON.');
    controller.dispose();
  });

  test('KIS live submit is disabled when KIS is disabled', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(kisEnabled: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(), 'KIS trading is disabled.');
    controller.dispose();
  });

  test('KIS live submit is disabled when real orders are disabled', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(kisRealOrderEnabled: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'KIS real-order submission is disabled.');
    controller.dispose();
  });

  test('KIS live submit is disabled when market is closed', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(marketOpen: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(), 'Market is closed.');
    controller.dispose();
  });

  test('KIS live submit is disabled when entry is not allowed now', () {
    final controller = _readyKisController(
      safetyStatus: _safetyStatus(entryAllowedNow: false),
    );

    expect(controller.canSubmitLiveKisOrder, isFalse);
    expect(controller.kisSubmitBlockedMessage(),
        'Market entry is not allowed now.');
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
  int mockCalls = 0;
  int getOpsSettingsCalls = 0;
  int updateOpsSettingsCalls = 0;
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
      throw const ApiRequestException('HTTP 500: {"message":"settings failed"}');
    }
  }

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async =>
      SchedulerStatus.safeDefault();

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
