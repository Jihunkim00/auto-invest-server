import 'candidate.dart';
import 'watchlist_operator_summary.dart';

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
    this.operatorSummary,
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
  final WatchlistOperatorSummary? operatorSummary;

  factory WatchlistRunResult.fromJson(Map<String, dynamic> json) {
    final run = parseMap(json['run']);
    final tradeResult = parseMap(json['trade_result']);

    List<Candidate> parseCandidates(Object? raw,
        {String scoreKey = 'score', String noteKey = 'note'}) {
      if (raw is List) {
        return raw
            .map((item) =>
                parseCandidate(item, scoreKey: scoreKey, noteKey: noteKey))
            .whereType<Candidate>()
            .toList();
      }
      final single = parseCandidate(raw, scoreKey: scoreKey, noteKey: noteKey);
      return single == null ? <Candidate>[] : <Candidate>[single];
    }

    String stringifySymbolField(Object? value) {
      final parsed = parseCandidates(value,
          scoreKey: 'final_entry_score', noteKey: 'reason');
      if (parsed.isNotEmpty && parsed.first.symbol.isNotEmpty) {
        return parsed.first.symbol;
      }
      return parseNullableString(value) ?? '';
    }

    List<String> parseCandidateSymbolList(Object? raw) {
      if (raw is List) {
        return raw
            .map(stringifySymbolField)
            .where((item) => item.isNotEmpty)
            .toList();
      }
      final symbol = stringifySymbolField(raw);
      return symbol.isEmpty ? <String>[] : <String>[symbol];
    }

    final finalBestCandidates = parseCandidates(json['final_best_candidate'],
        scoreKey: 'final_entry_score', noteKey: 'reason');
    final finalBestCandidate =
        finalBestCandidates.isEmpty ? null : finalBestCandidates.first;
    final finalRankedCandidates = parseCandidates(
        json['final_ranked_candidates'] ?? json['candidates'],
        scoreKey: 'final_entry_score',
        noteKey: 'reason');
    final effectiveFinalRankedCandidates = finalRankedCandidates.isNotEmpty
        ? finalRankedCandidates
        : finalBestCandidates;
    final effectiveBestCandidate = finalBestCandidate ??
        (effectiveFinalRankedCandidates.isEmpty
            ? null
            : effectiveFinalRankedCandidates.first);
    final researchedCandidates = parseCandidates(json['researched_candidates'],
        scoreKey: 'final_entry_score', noteKey: 'reason');

    return WatchlistRunResult(
      configuredSymbolCount: parseInt(json['configured_symbol_count']),
      analyzedSymbolCount: parseInt(json['analyzed_symbol_count']),
      quantCandidatesCount: parseInt(json['quant_candidates_count']),
      researchedCandidatesCount: parseInt(json['researched_candidates_count']),
      finalBestCandidate: _firstText([
        effectiveBestCandidate?.symbol,
        stringifySymbolField(json['final_best_candidate']),
      ]),
      secondFinalCandidate:
          stringifySymbolField(json['second_final_candidate']),
      tiedFinalCandidates:
          parseCandidateSymbolList(json['tied_final_candidates']),
      nearTiedCandidates:
          parseCandidateSymbolList(json['near_tied_candidates']),
      tieBreakerApplied:
          parseNullableBool(json['tie_breaker_applied']) ?? false,
      finalCandidateSelectionReason:
          parseNullableString(json['final_candidate_selection_reason']) ?? '',
      bestScore: parseNullableDouble(json['best_score']) ??
          effectiveBestCandidate?.entryScore ??
          effectiveBestCandidate?.finalEntryScore,
      finalScoreGap: parseNullableDouble(json['final_score_gap']),
      minEntryScore: parseNullableInt(json['min_entry_score']),
      minScoreGap: parseNullableInt(json['min_score_gap']),
      shouldTrade: parseNullableBool(json['should_trade']) ?? false,
      triggeredSymbol: parseNullableString(json['triggered_symbol']),
      triggerBlockReason: parseNullableString(json['trigger_block_reason']) ??
          effectiveBestCandidate?.blockReason ??
          '',
      finalEntryReady: parseNullableBool(json['final_entry_ready']) == true ||
          effectiveBestCandidate?.entryReady == true,
      finalActionHint: effectiveBestCandidate?.actionHint ??
          parseNullableString(json['final_action_hint']) ??
          'watch',
      action: parseNullableString(tradeResult?['action']) ??
          parseNullableString(json['action']) ??
          '',
      orderId: parseNullableString(tradeResult?['order_id']) ??
          parseNullableString(json['order_id']) ??
          effectiveBestCandidate?.orderId ??
          effectiveBestCandidate?.relatedOrderId,
      topQuantCandidates: parseCandidates(json['top_quant_candidates'],
          scoreKey: 'quant_score', noteKey: 'quant_reason'),
      researchedCandidates: researchedCandidates,
      finalRankedCandidates: effectiveFinalRankedCandidates,
      result: _firstText([
        parseNullableString(run?['result']),
        parseNullableString(tradeResult?['result']),
        parseNullableString(tradeResult?['status']),
        parseNullableString(tradeResult?['action']),
        parseNullableString(json['result']),
        parseNullableString(json['status']),
        effectiveBestCandidate?.result,
        effectiveBestCandidate?.status,
      ]),
      reason: _firstText([
        parseNullableString(run?['reason']),
        parseNullableString(tradeResult?['reason']),
        parseNullableString(json['reason']),
        effectiveBestCandidate?.noOrderReason,
        effectiveBestCandidate?.skipReason,
        effectiveBestCandidate?.blockReason,
        effectiveBestCandidate?.reason,
      ]),
      triggerSource: parseNullableString(run?['trigger_source']) ??
          parseNullableString(json['trigger_source']) ??
          'manual',
      operatorSummary: WatchlistOperatorSummary.fromJson(
        json['operator_summary'] ?? json['operatorSummary'],
      ),
    );
  }
}

Map<String, dynamic>? parseMap(Object? raw) {
  if (raw is Map<String, dynamic>) return raw;
  if (raw is Map) return Map<String, dynamic>.from(raw);
  return null;
}

Candidate? parseCandidate(Object? raw,
    {String scoreKey = 'score', String noteKey = 'note'}) {
  if (raw is List) {
    for (final item in raw) {
      final candidate =
          parseCandidate(item, scoreKey: scoreKey, noteKey: noteKey);
      if (candidate != null) return candidate;
    }
    return null;
  }
  final map = parseMap(raw);
  if (map == null) return null;
  return Candidate.fromJson(map, scoreKey: scoreKey, noteKey: noteKey);
}

double? parseNullableDouble(Object? raw) {
  if (raw == null) return null;
  if (raw is num) return raw.toDouble();
  final text = raw.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

int parseInt(Object? raw, {int fallback = 0}) {
  if (raw is num) return raw.toInt();
  final text = raw?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return int.tryParse(text) ?? double.tryParse(text)?.toInt() ?? fallback;
}

int? parseNullableInt(Object? raw) {
  if (raw == null) return null;
  if (raw is num) return raw.toInt();
  final text = raw.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text) ?? double.tryParse(text)?.toInt();
}

String? parseNullableString(Object? raw) {
  final text = raw?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

bool? parseNullableBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

String _firstText(List<String?> values) {
  for (final value in values) {
    final text = value?.trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return '';
}
