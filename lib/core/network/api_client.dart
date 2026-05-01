import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../../models/candidate.dart';
import '../../models/log_items.dart';
import '../../models/manual_trading_run_result.dart';
import '../../models/ops_settings.dart';
import '../../models/portfolio_summary.dart';
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

  static int _readInt(Object? value, int fallback) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? fallback;
  }

  Future<Map<String, dynamic>> _getJson(String path) async {
    final r = await _client.get(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _postJson(String path) async {
    final r = await _client.post(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
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
