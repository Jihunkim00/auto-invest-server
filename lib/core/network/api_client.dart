import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../../models/candidate.dart';
import '../../models/manual_trading_run_result.dart';
import '../../models/ops_settings.dart';
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

  static Map<String, dynamic> _readMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    return <String, dynamic>{};
  }

  static String? _readNullableString(Object? value) {
    final text = value?.toString();
    if (text == null || text.isEmpty) return null;
    return text;
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
      final j = await _getJson('/ops/runs?limit=50');
      final list =
          (j['runs'] as List<dynamic>? ?? j['items'] as List<dynamic>? ?? []);
      return list.whereType<Map<String, dynamic>>().map((e) {
        final responsePayload = _readMap(e['response_payload']);
        final tradeResult = _readMap(responsePayload['trade_result']);
        return TradingRun(
          timestamp: (e['created_at'] ?? e['timestamp'] ?? '').toString(),
          triggerSource: (e['trigger_source'] ?? 'manual').toString(),
          symbol: (e['symbol'] ?? 'WMT').toString(),
          result: (e['result'] ?? 'skipped').toString(),
          reason: (e['reason'] ??
                  responsePayload['reason'] ??
                  tradeResult['reason'] ??
                  '')
              .toString(),
          bestScore:
              _readInt(e['best_score'] ?? responsePayload['best_score'], 0),
          orderId: _readNullableString(e['order_id'] ??
              responsePayload['related_order_id'] ??
              tradeResult['order_id']),
          action: (responsePayload['action'] ??
                  tradeResult['action'] ??
                  e['action'] ??
                  'hold')
              .toString(),
          gateLevel: _readInt(e['gate_level'], 0),
        );
      }).toList();
    } catch (_) {
      return mockRuns;
    }
  }

  Future<List<Map<String, dynamic>>> getRecentOrders() async =>
      [(await _getJson('/orders/recent'))];
  Future<List<Map<String, dynamic>>> getRecentSignals() async =>
      [(await _getJson('/signals/recent'))];

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
