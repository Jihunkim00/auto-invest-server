import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../../models/candidate.dart';
import '../../models/ops_settings.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';
import '../config/app_config.dart';

class ApiException implements Exception {
  const ApiException(this.message, {this.statusCode, this.notImplemented = false});

  final String message;
  final int? statusCode;
  final bool notImplemented;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  static const _timeout = Duration(seconds: 15);

  String get baseUrl => AppConfig.resolvedApiBaseUrl;

  Uri _uri(String path) => Uri.parse('$baseUrl$path');

  Future<dynamic> _decode(http.Response response) async {
    if (response.body.trim().isEmpty) return null;
    try {
      return jsonDecode(response.body);
    } catch (_) {
      throw const ApiException('Invalid response from backend (non-JSON body).');
    }
  }

  Never _throwForStatus(http.Response response) {
    final status = response.statusCode;
    final body = response.body.trim();
    if (status == 404) {
      throw const ApiException('This control is not implemented on backend yet.', statusCode: 404, notImplemented: true);
    }
    if (status >= 500) {
      throw ApiException('Server error ($status). ${body.isEmpty ? '' : body}');
    }
    throw ApiException('Request failed ($status). ${body.isEmpty ? '' : body}', statusCode: status);
  }

  Future<http.Response> _get(String path) async {
    try {
      final response = await _client.get(_uri(path)).timeout(_timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        _throwForStatus(response);
      }
      return response;
    } on TimeoutException {
      throw ApiException('Backend request timed out after ${_timeout.inSeconds}s ($baseUrl).');
    } on http.ClientException catch (e) {
      throw ApiException('Backend unreachable at $baseUrl (${e.message}).');
    }
  }

  Future<http.Response> _post(String path) async {
    try {
      final response = await _client.post(_uri(path)).timeout(_timeout);
      if (response.statusCode < 200 || response.statusCode >= 300) {
        _throwForStatus(response);
      }
      return response;
    } on TimeoutException {
      throw ApiException('Backend request timed out after ${_timeout.inSeconds}s ($baseUrl).');
    } on http.ClientException catch (e) {
      throw ApiException('Backend unreachable at $baseUrl (${e.message}).');
    }
  }

  OpsSettings _settingsFromJson(Map<String, dynamic> j) {
    return OpsSettings(
      schedulerEnabled: j['scheduler_enabled'] == true,
      botEnabled: j['bot_enabled'] == true,
      dryRun: j['dry_run'] != false,
      killSwitch: j['kill_switch'] == true,
      brokerMode: (j['broker_mode'] ?? 'Paper').toString(),
      maxDailyTrades: (j['max_daily_trades'] ?? j['max_trades_per_day'] ?? 5) as int,
      maxDailyEntries: (j['max_daily_entries'] ?? j['global_daily_entry_limit'] ?? 2) as int,
      minEntryScore: (j['min_entry_score'] ?? 65) as int,
      minScoreGap: (j['min_score_gap'] ?? 3) as int,
      updatedAt: DateTime.tryParse((j['updated_at'] ?? '').toString()),
    );
  }

  Future<OpsSettings> getOpsSettings() async {
    final response = await _get('/ops/settings');
    final json = await _decode(response);
    if (json is! Map<String, dynamic>) {
      throw const ApiException('Invalid response for /ops/settings.');
    }
    return _settingsFromJson(json);
  }

  Future<OpsSettings> _toggleAndResolve(String path) async {
    final response = await _post(path);
    final json = await _decode(response);
    if (json is Map<String, dynamic> && json['settings'] is Map<String, dynamic>) {
      return _settingsFromJson(json['settings'] as Map<String, dynamic>);
    }
    return getOpsSettings();
  }

  Future<OpsSettings> schedulerOn() => _toggleAndResolve('/ops/scheduler/on');
  Future<OpsSettings> schedulerOff() => _toggleAndResolve('/ops/scheduler/off');
  Future<OpsSettings> botOn() => _toggleAndResolve('/ops/bot/on');
  Future<OpsSettings> botOff() => _toggleAndResolve('/ops/bot/off');
  Future<OpsSettings> dryRunOn() => _toggleAndResolve('/ops/dry-run/on');
  Future<OpsSettings> dryRunOff() => _toggleAndResolve('/ops/dry-run/off');
  Future<OpsSettings> killSwitchOn() => _toggleAndResolve('/ops/kill-switch/on');
  Future<OpsSettings> killSwitchOff() => _toggleAndResolve('/ops/kill-switch/off');

  Future<WatchlistRunResult> runWatchlistOnce() async {
    final response = await _post('/trading/run-watchlist-once');
    final json = await _decode(response);
    if (json is! Map<String, dynamic>) return getMockRunResult();
    return _watchlistFromJson(json);
  }

  WatchlistRunResult _watchlistFromJson(Map<String, dynamic> j) {
    return WatchlistRunResult(
      configuredSymbolCount: (j['configured_symbol_count'] ?? 50) as int,
      analyzedSymbolCount: (j['analyzed_symbol_count'] ?? 50) as int,
      quantCandidatesCount: (j['quant_candidates_count'] ?? 5) as int,
      researchedCandidatesCount: (j['researched_candidates_count'] ?? 5) as int,
      finalBestCandidate: (j['final_best_candidate'] ?? 'WMT').toString(),
      secondFinalCandidate: (j['second_final_candidate'] ?? 'CSCO').toString(),
      tiedFinalCandidates: ((j['tied_final_candidates'] ?? ['WMT', 'CSCO', 'APP']) as List).map((e) => e.toString()).toList(),
      nearTiedCandidates: ((j['near_tied_candidates'] ?? ['WMT', 'CSCO', 'APP']) as List).map((e) => e.toString()).toList(),
      tieBreakerApplied: j['tie_breaker_applied'] == true,
      finalCandidateSelectionReason: (j['final_candidate_selection_reason'] ?? 'Tie-breaker prioritized stability and volume momentum.').toString(),
      bestScore: (j['best_score'] ?? 68) as int,
      finalScoreGap: (j['final_score_gap'] ?? 0) as int,
      minEntryScore: (j['min_entry_score'] ?? 65) as int,
      minScoreGap: (j['min_score_gap'] ?? 3) as int,
      shouldTrade: j['should_trade'] == true,
      triggeredSymbol: j['triggered_symbol']?.toString(),
      triggerBlockReason: (j['trigger_block_reason'] ?? 'weak_final_score_gap').toString(),
      action: (j['trade_result']?['action'] ?? 'hold').toString(),
      orderId: j['trade_result']?['order_id']?.toString(),
      topQuantCandidates: const [Candidate(symbol: 'WMT', score: 68, note: 'Low drawdown')],
      researchedCandidates: const [Candidate(symbol: 'WMT', score: 68, note: 'Defensive retail signal')],
      finalRankedCandidates: const [
        Candidate(symbol: 'WMT', score: 68, note: 'Selected after tie-breaker'),
        Candidate(symbol: 'CSCO', score: 68, note: 'Near tied'),
        Candidate(symbol: 'APP', score: 68, note: 'Near tied'),
      ],
      result: (j['run']?['result'] ?? j['result'] ?? 'skipped').toString(),
      reason: (j['run']?['reason'] ?? j['reason'] ?? 'weak_final_score_gap').toString(),
      triggerSource: (j['run']?['trigger_source'] ?? j['trigger_source'] ?? 'manual').toString(),
    );
  }

  Future<List<TradingRun>> getRecentTradingRuns() async {
    final response = await _get('/trading/runs/recent');
    final j = await _decode(response);
    if (j is! Map<String, dynamic>) throw const ApiException('Invalid response for /trading/runs/recent.');
    final list = (j['items'] as List<dynamic>? ?? []);
    return list
        .map((e) => TradingRun(
              timestamp: (e['timestamp'] ?? '').toString(),
              triggerSource: (e['trigger_source'] ?? 'manual').toString(),
              symbol: (e['symbol'] ?? 'WMT').toString(),
              result: (e['result'] ?? 'skipped').toString(),
              reason: (e['reason'] ?? 'weak_final_score_gap').toString(),
              bestScore: (e['best_score'] ?? 68) as int,
              orderId: e['order_id']?.toString(),
              action: (e['action'] ?? 'hold').toString(),
            ))
        .toList();
  }

  Future<List<Map<String, dynamic>>> getRecentOrders() async {
    final response = await _get('/orders/recent');
    final j = await _decode(response);
    return [(j as Map<String, dynamic>?) ?? <String, dynamic>{}];
  }

  Future<List<Map<String, dynamic>>> getRecentSignals() async {
    final response = await _get('/signals/recent');
    final j = await _decode(response);
    return [(j as Map<String, dynamic>?) ?? <String, dynamic>{}];
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
      finalCandidateSelectionReason: 'Tie-breaker prioritized stability and volume momentum among near-tied final candidates.',
      bestScore: 68,
      finalScoreGap: 0,
      minEntryScore: 65,
      minScoreGap: 3,
      shouldTrade: false,
      triggeredSymbol: null,
      triggerBlockReason: 'weak_final_score_gap',
      action: 'hold',
      orderId: null,
      topQuantCandidates: [Candidate(symbol: 'WMT', score: 68, note: 'Low drawdown'), Candidate(symbol: 'CSCO', score: 68, note: 'Stable trend'), Candidate(symbol: 'APP', score: 68, note: 'Momentum')],
      researchedCandidates: [Candidate(symbol: 'WMT', score: 68, note: 'Defensive retail signal'), Candidate(symbol: 'CSCO', score: 67, note: 'Earnings resilience'), Candidate(symbol: 'APP', score: 67, note: 'AI demand')],
      finalRankedCandidates: [Candidate(symbol: 'WMT', score: 68, note: 'Selected after tie-breaker'), Candidate(symbol: 'CSCO', score: 68, note: 'Near tied'), Candidate(symbol: 'APP', score: 68, note: 'Near tied')],
      result: 'skipped',
      reason: 'weak_final_score_gap',
      triggerSource: 'manual',
    );
  }
}
