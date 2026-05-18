String displayScore(num? value, {String fallback = 'Score not returned'}) {
  if (value == null) return fallback;
  final numeric = value.toDouble();
  return numeric.toStringAsFixed(numeric.truncateToDouble() == numeric ? 0 : 2);
}

String compactScore(num? value) => displayScore(value, fallback: '--');

String displayText(Object? value, {String fallback = 'Not available'}) {
  final text = value?.toString().trim() ?? '';
  if (text.isEmpty || text == 'null') return fallback;
  return text;
}

String firstText(List<String?> values, {String fallback = ''}) {
  for (final value in values) {
    final text = value?.trim();
    if (text != null && text.isNotEmpty && text != 'null') return text;
  }
  return fallback;
}

String translateReason(Object? value, {num? entryPenalty}) {
  if (entryPenalty != null && entryPenalty >= 900) {
    return 'Entry blocked by GPT/risk context';
  }
  final text = displayText(value, fallback: '');
  if (text.isEmpty) return 'Not available';
  final normalized = text.toLowerCase();
  if (normalized == 'score_threshold_not_met') {
    return 'Score below entry threshold';
  }
  if (normalized == 'hard_blocked') {
    return 'Entry blocked by risk context';
  }
  if (normalized == 'gpt_hard_block_new_buy') {
    return 'GPT/risk context blocks new buy entries';
  }
  if (normalized == 'kr_trading_disabled') {
    return 'KR trading disabled / preview only';
  }
  if (normalized == 'market_closed') {
    return 'Market is closed';
  }
  if (normalized == 'preview_only') {
    return 'Preview only, no real order';
  }
  if (normalized == 'no_candidate') {
    return 'No candidate found';
  }
  if (normalized == 'risk_gate_blocked') {
    return 'Safety gate blocked';
  }
  if (normalized == 'all_candidates_blocked') {
    return 'Safety gate blocked';
  }
  if (normalized == 'gpt_unavailable') {
    return 'GPT advisory unavailable';
  }
  if (normalized == 'hold_signal') {
    return 'HOLD signal, no order created';
  }
  if (normalized == 'buy_entry_not_allowed_now') {
    return 'New buy entries are not allowed now';
  }
  if (normalized == 'dry_run_must_be_false') {
    return 'Dry-run is ON, live order blocked';
  }
  if (normalized == 'kill_switch_enabled') {
    return 'Kill switch is ON';
  }
  if (normalized.contains('gpt_entry_penalty=999')) {
    return 'New buy blocked by GPT/risk context';
  }
  return text;
}

String boolStatus(bool value) => value ? 'true' : 'false';
