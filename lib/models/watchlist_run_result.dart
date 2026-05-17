import 'candidate.dart';

class WatchlistRunResult {
  const WatchlistRunResult({
    required this.configuredSymbolCount,
    required this.analyzedSymbolCount,
    required this.quantCandidatesCount,
    required this.researchedCandidatesCount,
    required this.finalBestCandidate,
    required this.secondFinalCandidate,
    required this.tiedFinalCandidates,
    required this.nearTiedCandidates,
    required this.tieBreakerApplied,
    required this.finalCandidateSelectionReason,
    required this.bestScore,
    required this.finalScoreGap,
    required this.minEntryScore,
    required this.minScoreGap,
    required this.shouldTrade,
    required this.triggeredSymbol,
    required this.triggerBlockReason,
    required this.finalEntryReady,
    required this.finalActionHint,
    required this.action,
    required this.orderId,
    required this.topQuantCandidates,
    required this.researchedCandidates,
    required this.finalRankedCandidates,
    required this.result,
    required this.reason,
    required this.triggerSource,
  });

  final int configuredSymbolCount;
  final int analyzedSymbolCount;
  final int quantCandidatesCount;
  final int researchedCandidatesCount;
  final String finalBestCandidate;
  final String secondFinalCandidate;
  final List<String> tiedFinalCandidates;
  final List<String> nearTiedCandidates;
  final bool tieBreakerApplied;
  final String finalCandidateSelectionReason;
  final double? bestScore;
  final double? finalScoreGap;
  final int? minEntryScore;
  final int? minScoreGap;
  final bool shouldTrade;
  final String? triggeredSymbol;
  final String triggerBlockReason;
  final bool finalEntryReady;
  final String finalActionHint;
  final String action;
  final String? orderId;
  final List<Candidate> topQuantCandidates;
  final List<Candidate> researchedCandidates;
  final List<Candidate> finalRankedCandidates;
  final String result;
  final String reason;
  final String triggerSource;

  factory WatchlistRunResult.fromJson(Map<String, dynamic> json) {
    final run = json['run'] as Map<String, dynamic>?;
    final tradeResult = json['trade_result'] as Map<String, dynamic>?;

    String stringifySymbolField(Object? value) {
      if (value is Map<String, dynamic>) {
        return value['symbol']?.toString() ?? '';
      }
      return value?.toString() ?? '';
    }

    List<String> parseCandidateSymbolList(Object? raw) {
      if (raw is List) {
        return raw
            .map((item) {
              if (item is Map<String, dynamic>) {
                return item['symbol']?.toString() ?? '';
              }
              return item?.toString() ?? '';
            })
            .where((item) => item.isNotEmpty)
            .toList();
      }
      return <String>[];
    }

    Map<String, dynamic>? parseMap(Object? raw) {
      if (raw is Map<String, dynamic>) return raw;
      if (raw is Map) return Map<String, dynamic>.from(raw);
      return null;
    }

    Candidate? parseCandidate(Object? raw,
        {String scoreKey = 'score', String noteKey = 'note'}) {
      final map = parseMap(raw);
      if (map == null) return null;
      return Candidate.fromJson(map, scoreKey: scoreKey, noteKey: noteKey);
    }

    List<Candidate> parseCandidates(Object? raw,
        {String scoreKey = 'score', String noteKey = 'note'}) {
      if (raw is List) {
        return raw
            .map((item) => parseCandidate(item,
                scoreKey: scoreKey, noteKey: noteKey))
            .whereType<Candidate>()
            .toList();
      }
      final single = parseCandidate(raw, scoreKey: scoreKey, noteKey: noteKey);
      return single == null ? <Candidate>[] : <Candidate>[single];
    }

    double? parseNullableDouble(Object? raw) {
      if (raw == null) return null;
      if (raw is num) return raw.toDouble();
      final text = raw.toString().trim();
      if (text.isEmpty) return null;
      return double.tryParse(text);
    }

    int parseInt(Object? raw, {int fallback = 0}) {
      if (raw is num) return raw.toInt();
      return int.tryParse(raw?.toString() ?? '') ?? fallback;
    }

    int? parseNullableInt(Object? raw) {
      if (raw == null) return null;
      if (raw is num) return raw.toInt();
      final text = raw.toString().trim();
      if (text.isEmpty || text == 'null') return null;
      return int.tryParse(text) ?? double.tryParse(text)?.toInt();
    }

    String? parseNullableString(Object? raw) {
      final text = raw?.toString().trim();
      if (text == null || text.isEmpty || text == 'null') return null;
      return text;
    }

    final finalBestCandidate = parseCandidate(json['final_best_candidate'],
        scoreKey: 'final_entry_score', noteKey: 'reason');
    final finalRankedCandidates = parseCandidates(
        json['final_ranked_candidates'] ?? json['candidates'],
        scoreKey: 'final_entry_score',
        noteKey: 'reason');
    final researchedCandidates = parseCandidates(json['researched_candidates'],
        scoreKey: 'final_entry_score', noteKey: 'reason');
    final effectiveFinalRankedCandidates = finalRankedCandidates.isNotEmpty
        ? finalRankedCandidates
        : finalBestCandidate == null
            ? <Candidate>[]
            : <Candidate>[finalBestCandidate];

    return WatchlistRunResult(
      configuredSymbolCount: parseInt(json['configured_symbol_count']),
      analyzedSymbolCount: parseInt(json['analyzed_symbol_count']),
      quantCandidatesCount: parseInt(json['quant_candidates_count']),
      researchedCandidatesCount: parseInt(json['researched_candidates_count']),
      finalBestCandidate: stringifySymbolField(json['final_best_candidate']),
      secondFinalCandidate:
          stringifySymbolField(json['second_final_candidate']),
      tiedFinalCandidates:
          parseCandidateSymbolList(json['tied_final_candidates']),
      nearTiedCandidates:
          parseCandidateSymbolList(json['near_tied_candidates']),
      tieBreakerApplied: json['tie_breaker_applied'] == true,
      finalCandidateSelectionReason:
          json['final_candidate_selection_reason']?.toString() ?? '',
      bestScore: parseNullableDouble(json['best_score']),
      finalScoreGap: parseNullableDouble(json['final_score_gap']),
      minEntryScore: parseNullableInt(json['min_entry_score']),
      minScoreGap: parseNullableInt(json['min_score_gap']),
      shouldTrade: json['should_trade'] == true,
      triggeredSymbol: json['triggered_symbol']?.toString(),
      triggerBlockReason: json['trigger_block_reason']?.toString() ?? '',
      finalEntryReady:
          json['final_entry_ready'] == true || finalBestCandidate?.entryReady == true,
      finalActionHint: finalBestCandidate?.actionHint ??
          json['final_action_hint']?.toString() ??
          'watch',
      action: tradeResult?['action']?.toString() ??
          json['action']?.toString() ??
          '',
      orderId: parseNullableString(tradeResult?['order_id']) ??
          parseNullableString(json['order_id']),
      topQuantCandidates: parseCandidates(json['top_quant_candidates'],
          scoreKey: 'quant_score', noteKey: 'quant_reason'),
      researchedCandidates: researchedCandidates,
      finalRankedCandidates: effectiveFinalRankedCandidates,
      result: run?['result']?.toString() ??
          tradeResult?['result']?.toString() ??
          tradeResult?['status']?.toString() ??
          tradeResult?['action']?.toString() ??
          json['result']?.toString() ??
          json['status']?.toString() ??
          '',
      reason: run?['reason']?.toString() ??
          tradeResult?['reason']?.toString() ??
          json['reason']?.toString() ??
          finalBestCandidate?.reason ??
          '',
      triggerSource: run?['trigger_source']?.toString() ??
          json['trigger_source']?.toString() ??
          'manual',
    );
  }
}
