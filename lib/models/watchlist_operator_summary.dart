import 'candidate.dart';

class WatchlistOperatorSummary {
  const WatchlistOperatorSummary({
    required this.mode,
    required this.previewOnly,
    required this.tradingEnabled,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.completedGptCount,
    required this.notRunCount,
    required this.failedCount,
    required this.topGptCandidates,
    required this.bestCandidate,
    required this.topRiskFlags,
    required this.topGatingNotes,
    required this.conservativeDecisionSummary,
    required this.nextManualActionHint,
  });

  final String mode;
  final bool previewOnly;
  final bool tradingEnabled;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int completedGptCount;
  final int notRunCount;
  final int failedCount;
  final List<Candidate> topGptCandidates;
  final Candidate? bestCandidate;
  final List<String> topRiskFlags;
  final List<String> topGatingNotes;
  final String conservativeDecisionSummary;
  final String nextManualActionHint;

  static WatchlistOperatorSummary? fromJson(Object? raw) {
    final json = _readMap(raw);
    if (json == null) return null;
    return WatchlistOperatorSummary(
      mode: _readNullableString(json['mode']) ?? '',
      previewOnly: _readNullableBool(json['preview_only']) ?? false,
      tradingEnabled: _readNullableBool(json['trading_enabled']) ?? false,
      realOrderSubmitted:
          _readNullableBool(json['real_order_submitted']) ?? false,
      brokerSubmitCalled:
          _readNullableBool(json['broker_submit_called']) ?? false,
      manualSubmitCalled:
          _readNullableBool(json['manual_submit_called']) ?? false,
      completedGptCount: _readInt(json['completed_gpt_count']),
      notRunCount: _readInt(json['not_run_count']),
      failedCount: _readInt(json['failed_count']),
      topGptCandidates: _readCandidateList(json['top_gpt_candidates']),
      bestCandidate: _readCandidate(json['best_candidate']),
      topRiskFlags: _readStringList(json['top_risk_flags']),
      topGatingNotes: _readStringList(json['top_gating_notes']),
      conservativeDecisionSummary:
          _readNullableString(json['conservative_decision_summary']) ?? '',
      nextManualActionHint:
          _readNullableString(json['next_manual_action_hint']) ?? '',
    );
  }
}

List<Candidate> _readCandidateList(Object? raw) {
  if (raw is! List) return const [];
  return raw.map(_readCandidate).whereType<Candidate>().toList();
}

Candidate? _readCandidate(Object? raw) {
  final map = _readMap(raw);
  if (map == null) return null;
  final normalized = Map<String, dynamic>.from(map);
  if (!normalized.containsKey('risk_flags') &&
      normalized['main_risk_flags'] is List) {
    normalized['risk_flags'] = normalized['main_risk_flags'];
  }
  if (!normalized.containsKey('reason') && normalized['short_reason'] != null) {
    normalized['reason'] = normalized['short_reason'];
  }
  if (!normalized.containsKey('note') && normalized['short_reason'] != null) {
    normalized['note'] = normalized['short_reason'];
  }
  if (!normalized.containsKey('score') &&
      normalized['final_buy_score'] != null) {
    normalized['score'] = normalized['final_buy_score'];
  }
  return Candidate.fromJson(normalized);
}

Map<String, dynamic>? _readMap(Object? raw) {
  if (raw is Map<String, dynamic>) return raw;
  if (raw is Map) return Map<String, dynamic>.from(raw);
  return null;
}

int _readInt(Object? raw, {int fallback = 0}) {
  if (raw is num) return raw.toInt();
  final text = raw?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return int.tryParse(text) ?? double.tryParse(text)?.toInt() ?? fallback;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

bool? _readNullableBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

List<String> _readStringList(Object? value) {
  if (value is List) {
    return value
        .map((item) => item.toString().trim())
        .where((item) => item.isNotEmpty && item != 'null')
        .toList();
  }
  final text = _readNullableString(value);
  return text == null ? const [] : <String>[text];
}
