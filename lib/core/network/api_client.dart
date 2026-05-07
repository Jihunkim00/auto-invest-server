import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../../models/candidate.dart';
import '../../models/kis_manual_order_result.dart';
import '../../models/kis_manual_order_safety_status.dart';
import '../../models/log_items.dart';
import '../../models/market_watchlist.dart';
import '../../models/manual_trading_run_result.dart';
import '../../models/order_validation_result.dart';
import '../../models/ops_settings.dart';
import '../../models/portfolio_summary.dart';
import '../../models/scheduler_status.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';

class ApiRequestException implements Exception {
  const ApiRequestException(this.message);

  final String message;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  static const _kisLiveConfirmationPhrase =
      'I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER';

  static int _readInt(Object? value, int fallback) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? fallback;
  }

  static double? _readNullableDouble(Object? value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    final text = value.toString().trim().replaceAll(',', '');
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }

  Future<Map<String, dynamic>> _getJson(String path) async {
    final r = await _client.get(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _getJsonNoCache(String path) async {
    final uri = Uri.parse('${AppConfig.baseUrl}$path').replace(
      queryParameters: {
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );
    final r = await _client.get(uri, headers: const {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    });
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<Map<String, dynamic>> _postJson(String path) async {
    final r = await _client.post(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _postJsonBody(
      String path, Map<String, dynamic> body) async {
    final r = await _client.post(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<Map<String, dynamic>> _putJsonBody(
      String path, Map<String, dynamic> body) async {
    final r = await _client.put(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<void> _post(String path) async {
    final r = await _client.post(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
  }

  Future<PortfolioSummary> fetchPortfolioSummary() async {
    final uri = Uri.parse('${AppConfig.baseUrl}/portfolio/summary').replace(
      queryParameters: {
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );

    try {
      final r = await _client.get(uri, headers: const {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
      });
      if (r.statusCode == 404 || r.statusCode == 204) {
        return PortfolioSummary.empty();
      }
      if (r.statusCode >= 400) {
        throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
      }

      final decoded = jsonDecode(r.body);
      if (decoded is! Map) {
        throw const ApiRequestException('Invalid portfolio summary response.');
      }

      return PortfolioSummary.fromJson(Map<String, dynamic>.from(decoded));
    } on http.ClientException {
      return PortfolioSummary.empty();
    }
  }

  Future<PortfolioSummary> fetchUsPortfolioSummary() => fetchPortfolioSummary();
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
  }

  Future<PortfolioSummary> fetchKrPortfolioSummary() async {
    final balance = await _getJsonNoCache('/kis/account/balance');
    final positionsPayload = await _getJsonNoCache('/kis/account/positions');
    final ordersPayload = await _getJsonNoCache('/kis/account/open-orders');

    final rawPositions =
        positionsPayload['positions'] as List<dynamic>? ?? const [];
    final positions = rawPositions
        .whereType<Map>()
        .map((item) => PositionSummary.fromJson(
            Map<String, dynamic>.from(item.cast<String, dynamic>())))
        .toList();

    final rawOrders = ordersPayload['orders'] as List<dynamic>? ?? const [];
    final pendingOrders = rawOrders
        .whereType<Map>()
        .map((item) => PendingOrderSummary.fromJson(
            Map<String, dynamic>.from(item.cast<String, dynamic>())))
        .toList();

    final summedCostBasis = positions.fold<double>(
        0, (total, position) => total + position.costBasis);
    final summedMarketValue = positions.fold<double>(
        0, (total, position) => total + position.marketValue);
    final summedUnrealizedPl = positions.fold<double>(
        0, (total, position) => total + position.unrealizedPl);

    final totalCostBasis =
        _readNullableDouble(balance['purchase_amount']) ?? summedCostBasis;
    final totalMarketValue =
        _readNullableDouble(balance['stock_evaluation_amount']) ??
            _readNullableDouble(balance['total_market_value']) ??
            _readNullableDouble(balance['total_asset_value']) ??
            summedMarketValue;
    final totalUnrealizedPl =
        _readNullableDouble(balance['unrealized_pl']) ?? summedUnrealizedPl;
    final totalUnrealizedPlpc =
        _readNullableDouble(balance['unrealized_plpc']) ??
            (totalCostBasis > 0 ? totalUnrealizedPl / totalCostBasis : 0);
    final cash = _readNullableDouble(balance['cash']) ??
        _readNullableDouble(balance['dnca_tot_amt']) ??
        0;

    return PortfolioSummary(
      currency: 'KRW',
      positionsCount: _readInt(positionsPayload['count'], positions.length),
      pendingOrdersCount:
          _readInt(ordersPayload['count'], pendingOrders.length),
      totalCostBasis: totalCostBasis,
      totalMarketValue: totalMarketValue,
      totalUnrealizedPl: totalUnrealizedPl,
      totalUnrealizedPlpc: totalUnrealizedPlpc,
      cash: cash,
      positions: positions,
      pendingOrders: pendingOrders,
    );
  }

  Future<MarketWatchlist> fetchMarketWatchlist(String market) async {
    final normalizedMarket = market.trim().toUpperCase();
    try {
      final payload =
          await _getJsonNoCache('/market-profiles/$normalizedMarket/watchlist');
      return MarketWatchlist.fromJson(payload);
    } catch (_) {
      return MarketWatchlist.empty(normalizedMarket);
    }
  }

  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    final payload = await _getJsonNoCache('/kis/manual-order/status');
    return KisManualOrderSafetyStatus.fromJson(payload);
  }

  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
  }) async {
    final payload = await _postJsonBody('/kis/orders/validate', {
      'market': 'KR',
      'symbol': symbol.trim(),
      'side': side.trim().toLowerCase(),
      'qty': qty,
      'order_type': orderType,
      'dry_run': true,
      'reason': 'manual Flutter dashboard dry-run',
    });
    return OrderValidationResult.fromJson(payload);
  }

  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
  }) async {
    final payload = await _postJsonBody('/kis/orders/manual-submit', {
      'market': 'KR',
      'symbol': symbol.trim(),
      'side': side.trim().toLowerCase(),
      'qty': qty,
      'order_type': orderType,
      'dry_run': false,
      'confirm_live': confirmLive,
      'confirmation': confirmLive ? _kisLiveConfirmationPhrase : null,
      'reason': 'manual Flutter dashboard live KIS order',
    });
    return KisManualOrderResult.fromJson(payload);
  }

  Future<KisManualOrderResult> syncKisOrder(int orderId) async {
    final payload = await _postJsonBody('/kis/orders/$orderId/sync', const {});
    return KisManualOrderResult.fromJson(payload);
  }

  Future<KisOpenOrderSyncResult> syncOpenKisOrders() async {
    final payload = await _postJsonBody('/kis/orders/sync-open', const {});
    return KisOpenOrderSyncResult.fromJson(payload);
  }

  Future<Map<String, dynamic>> cancelKisOrder(int orderId) async {
    return _postJsonBody('/kis/orders/$orderId/cancel', const {});
  }

  Future<KisOrderSummary> fetchKisOrderSummary() async {
    final payload = await _getJsonNoCache('/kis/orders/summary');
    return KisOrderSummary.fromJson(payload);
  }

  Future<List<KisManualOrderResult>> fetchKisOrders({
    int limit = 20,
    bool includeRejected = false,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/orders').replace(
      queryParameters: {
        'limit': limit.toString(),
        if (includeRejected) 'include_rejected': 'true',
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );
    final r = await _client.get(uri, headers: const {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    });
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid KIS orders response.');
    }
    final rawOrders = decoded['orders'] as List<dynamic>? ?? const [];
    return rawOrders
        .whereType<Map>()
        .map((item) =>
            KisManualOrderResult.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<KisManualOrderResult> fetchKisOrderDetail(
    int orderId, {
    bool includeSyncPayload = false,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/orders/$orderId').replace(
      queryParameters: {
        if (includeSyncPayload) 'include_sync_payload': 'true',
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );
    final r = await _client.get(uri);
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    return KisManualOrderResult.fromJson(
        Map<String, dynamic>.from(jsonDecode(r.body) as Map));
  }

  Future<WatchlistRunResult> runKisWatchlistPreview({
    required int gateLevel,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/watchlist/preview').replace(
      queryParameters: {'gate_level': gateLevel.toString()},
    );
    final r = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(const {}),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    final payload = Map<String, dynamic>.from(decoded);
    return WatchlistRunResult.fromJson(payload);
  }

  Future<WatchlistRunResult> runWatchlistForProvider({
    required String provider,
    required int gateLevel,
  }) {
    final normalized = provider.trim().toLowerCase();
    if (normalized == 'kis') {
      return runKisWatchlistPreview(gateLevel: gateLevel);
    }
    return runWatchlistOnce();
  }

  Future<OpsSettings> getOpsSettings() async {
    try {
      final j = await _getJson('/ops/settings');
      return OpsSettings(
        schedulerEnabled: j['scheduler_enabled'] == true,
        botEnabled: j['bot_enabled'] == true,
        dryRun: j['dry_run'] != false,
        killSwitch: j['kill_switch'] == true,
        brokerMode: (j['broker_mode'] ?? 'Paper').toString(),
        defaultGateLevel: _readInt(j['default_gate_level'], 2),
        maxDailyTrades:
            _readInt(j['max_daily_trades'] ?? j['max_trades_per_day'], 5),
        maxDailyEntries: _readInt(
            j['max_daily_entries'] ?? j['global_daily_entry_limit'], 2),
        minEntryScore: _readInt(j['min_entry_score'], 65),
        minScoreGap: _readInt(j['min_score_gap'], 3),
      );
    } catch (_) {
      return const OpsSettings(
        schedulerEnabled: false,
        botEnabled: false,
        dryRun: true,
        killSwitch: false,
        brokerMode: 'Paper',
        defaultGateLevel: 2,
        maxDailyTrades: 5,
        maxDailyEntries: 2,
        minEntryScore: 65,
        minScoreGap: 3,
      );
    }
  }

  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    await _putJsonBody('/ops/settings', values);
  }

  Future<SchedulerStatus> fetchSchedulerStatus() async {
    try {
      final payload = await _getJsonNoCache('/scheduler/status');
      return SchedulerStatus.fromJson(payload);
    } catch (_) {
      return SchedulerStatus.safeDefault();
    }
  }

  Future<void> schedulerOn() => _post('/ops/scheduler/on');
  Future<void> schedulerOff() => _post('/ops/scheduler/off');
  Future<void> botOn() => _post('/ops/bot/on');
  Future<void> botOff() => _post('/ops/bot/off');
  Future<void> killSwitchOn() => _post('/ops/kill-switch/on');
  Future<void> killSwitchOff() => _post('/ops/kill-switch/off');
  Future<WatchlistRunResult> runWatchlistOnce() async {
    final j = await _postJson('/trading/run-watchlist-once');
    return WatchlistRunResult.fromJson(j);
  }

  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async {
    final uri = Uri.parse('${AppConfig.baseUrl}/trading/watchlist/latest')
        .replace(queryParameters: {
      '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
    });

    try {
      final r = await _client.get(uri, headers: const {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
      });
      if (r.statusCode == 404 || r.statusCode == 204) return null;
      if (r.statusCode >= 400) {
        throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
      }

      final decoded = jsonDecode(r.body);
      if (decoded is! Map) {
        throw const ApiRequestException('Invalid latest run response.');
      }

      final body = Map<String, dynamic>.from(decoded);
      final rawItem = body.containsKey('item') ? body['item'] : body;
      if (body['has_data'] == false || rawItem == null) return null;
      if (rawItem is! Map) {
        throw const ApiRequestException('Invalid latest run item.');
      }

      return WatchlistRunResult.fromJson(Map<String, dynamic>.from(rawItem));
    } on ApiRequestException {
      rethrow;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend response: $e');
    } on http.ClientException {
      throw const ApiRequestException(
          'Backend unreachable. Check API_BASE_URL and server status.');
    } catch (e) {
      throw ApiRequestException('Latest watchlist run unavailable: $e');
    }
  }

  Future<ManualTradingRunResult> runTradingOnce({
    required String symbol,
    required int gateLevel,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/trading/run-once').replace(
      queryParameters: {
        'symbol': symbol.trim().toUpperCase(),
        'gate_level': gateLevel.toString(),
        'trigger_source': 'manual',
      },
    );

    try {
      final r = await _client.post(uri);
      if (r.statusCode == 404) {
        throw const ApiRequestException(
            'Manual trading endpoint is not available on this backend.');
      }
      if (r.statusCode == 422) {
        throw ApiRequestException('Validation failed: ${r.body}');
      }
      if (r.statusCode >= 400) {
        throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
      }
      return ManualTradingRunResult.fromJson(
          jsonDecode(r.body) as Map<String, dynamic>);
    } on ApiRequestException {
      rethrow;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend response: $e');
    } on http.ClientException {
      throw const ApiRequestException(
          'Backend unreachable. Check API_BASE_URL and server status.');
    } catch (_) {
      throw const ApiRequestException(
          'Backend unreachable. Check API_BASE_URL and server status.');
    }
  }

  Future<List<TradingRun>> getRecentTradingRuns() async {
    try {
      final runs = await fetchRecentRuns(limit: 50);
      return runs.map((e) {
        return TradingRun(
          timestamp: e.createdAt,
          triggerSource: e.triggerSource,
          symbol: e.symbol,
          result: e.result,
          reason: e.reason,
          bestScore: 0,
          orderId: e.relatedOrderId,
          action: e.action,
          gateLevel: e.gateLevel,
        );
      }).toList();
    } catch (_) {
      return mockRuns;
    }
  }

  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    try {
      final j = await _getJson('/runs/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map<String, dynamic>>()
          .map(TradingLogItem.fromJson)
          .toList();
    } catch (_) {
      return mockTradingLogs;
    }
  }

  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    try {
      final j = await _getJson('/orders/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map<String, dynamic>>()
          .map(OrderLogItem.fromJson)
          .toList();
    } catch (_) {
      return mockOrderLogs;
    }
  }

  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    try {
      final j = await _getJson('/signals/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map<String, dynamic>>()
          .map(SignalLogItem.fromJson)
          .toList();
    } catch (_) {
      return mockSignalLogs;
    }
  }

  Future<LogsSummary> fetchLogsSummary() async {
    try {
      final j = await _getJson('/logs/summary');
      return LogsSummary.fromJson(j);
    } catch (_) {
      return mockLogsSummary;
    }
  }

  WatchlistRunResult getMockRunResult() {
    return const WatchlistRunResult(
      configuredSymbolCount: 50,
      analyzedSymbolCount: 50,
      quantCandidatesCount: 5,
      researchedCandidatesCount: 5,
      finalBestCandidate: 'WMT',
      secondFinalCandidate: 'CSCO',
      tiedFinalCandidates: ['WMT', 'CSCO', 'APP'],
      nearTiedCandidates: ['WMT', 'CSCO', 'APP'],
      tieBreakerApplied: true,
      finalCandidateSelectionReason:
          'Tie-breaker prioritized stability and volume momentum among near-tied final candidates.',
      bestScore: 68,
      finalScoreGap: 0,
      minEntryScore: 65,
      minScoreGap: 3,
      shouldTrade: false,
      triggeredSymbol: null,
      triggerBlockReason: 'weak_final_score_gap',
      finalEntryReady: false,
      finalActionHint: 'watch',
      action: 'hold',
      orderId: null,
      topQuantCandidates: [
        Candidate(
            symbol: 'WMT',
            score: 68,
            note: 'Low drawdown',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'CSCO',
            score: 68,
            note: 'Stable trend',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'APP',
            score: 68,
            note: 'Momentum',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap')
      ],
      researchedCandidates: [
        Candidate(
            symbol: 'WMT',
            score: 68,
            note: 'Defensive retail signal',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'CSCO',
            score: 67,
            note: 'Earnings resilience',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'APP',
            score: 67,
            note: 'AI demand',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap')
      ],
      finalRankedCandidates: [
        Candidate(
            symbol: 'WMT',
            score: 68,
            note: 'Selected after tie-breaker',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'CSCO',
            score: 68,
            note: 'Near tied',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'APP',
            score: 68,
            note: 'Near tied',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap')
      ],
      result: 'skipped',
      reason: 'weak_final_score_gap',
      triggerSource: 'manual',
    );
  }
}

const mockRuns = <TradingRun>[
  TradingRun(
      timestamp: '2026-04-26T12:20:00Z',
      triggerSource: 'manual',
      symbol: 'WMT',
      result: 'skipped',
      reason: 'weak_final_score_gap',
      bestScore: 68,
      orderId: null,
      action: 'hold',
      gateLevel: 2),
  TradingRun(
      timestamp: '2026-04-26T09:00:00Z',
      triggerSource: 'scheduler',
      symbol: 'CSCO',
      result: 'skipped',
      reason: 'weak_final_score_gap',
      bestScore: 67,
      orderId: null,
      action: 'hold',
      gateLevel: 2),
];
