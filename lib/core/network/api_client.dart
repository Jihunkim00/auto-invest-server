import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../../models/ops_settings.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';
import '../../models/candidate.dart';

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;

  Future<Map<String, dynamic>> _getJson(String path) async {
    final r = await _client.get(Uri.parse('${AppConfig.baseUrl}$path'));
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
        maxDailyTrades: (j['max_daily_trades'] ?? 5) as int,
        maxDailyEntries: (j['max_daily_entries'] ?? 3) as int,
        minEntryScore: (j['min_entry_score'] ?? 65) as int,
        minScoreGap: (j['min_score_gap'] ?? 3) as int,
      );
    } catch (_) {
      return const OpsSettings(
        schedulerEnabled: false,
        botEnabled: false,
        dryRun: true,
        killSwitch: false,
        brokerMode: 'Paper',
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
  Future<void> runWatchlistOnce() => _post('/trading/run-watchlist-once');

  Future<List<TradingRun>> getRecentTradingRuns() async {
    try {
      final j = await _getJson('/trading/runs/recent');
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
    } catch (_) {
      return mockRuns;
    }
  }

  Future<List<Map<String, dynamic>>> getRecentOrders() async => [(await _getJson('/orders/recent'))];
  Future<List<Map<String, dynamic>>> getRecentSignals() async => [(await _getJson('/signals/recent'))];

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

const mockRuns = <TradingRun>[
  TradingRun(timestamp: '2026-04-26T12:20:00Z', triggerSource: 'manual', symbol: 'WMT', result: 'skipped', reason: 'weak_final_score_gap', bestScore: 68, orderId: null, action: 'hold'),
  TradingRun(timestamp: '2026-04-26T09:00:00Z', triggerSource: 'scheduler', symbol: 'CSCO', result: 'skipped', reason: 'weak_final_score_gap', bestScore: 67, orderId: null, action: 'hold'),
];
