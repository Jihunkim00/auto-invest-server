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
  if (normalized == 'dry_run') {
    return 'Dry-run mode';
  }
  if (normalized == 'dry-run') {
    return 'Dry-run mode';
  }
  if (normalized == 'dry_run_must_be_false') {
    return 'Dry-run mode: no real order submitted';
  }
  if (normalized == 'hold_signal') {
    return 'HOLD signal, no order created';
  }
  if (normalized == 'buy_entry_not_allowed_now') {
    return 'New buy entries are not allowed now';
  }
  if (normalized == 'kill_switch_enabled') {
    return 'Kill switch is ON';
  }
  if (normalized == 'confirm_live_required') {
    return 'Live confirmation is required before submit';
  }
  if (normalized == 'kis_real_order_disabled') {
    return 'KIS real order disabled';
  }
  if (normalized == 'kis_disabled') {
    return 'KIS trading disabled';
  }
  if (normalized == 'quantity_or_amount_required') {
    return 'Quantity or amount is required';
  }
  if (normalized == 'symbol_mismatch') {
    return 'Returned candidate does not match selected symbol';
  }
  if (normalized == 'dry_run_mode') {
    return 'Dry-run mode: no real order submitted';
  }
  if (normalized == 'backend_risk_gate_blocked') {
    return 'Backend risk gate blocked this order';
  }
  if (normalized == 'order_validation_failed') {
    return 'Order validation failed';
  }
  if (normalized.contains('gpt_entry_penalty=999')) {
    return 'New buy blocked by GPT/risk context';
  }
  return text;
}

String boolStatus(bool value) => value ? 'true' : 'false';

String orderStatusLabel({
  required bool realOrderSubmitted,
  String? orderId,
  String? kisOdno,
  String? result,
  Map<String, dynamic> safety = const {},
}) {
  final normalized = result?.trim().toLowerCase() ?? '';
  if (realOrderSubmitted) return 'Real order submitted';
  if (normalized.contains('dry') ||
      safety['dry_run'] == true ||
      safety['runtime_dry_run'] == true) {
    return 'Dry-run, no real order';
  }
  if (normalized.contains('reject')) return 'Rejected';
  final id = firstText([orderId, kisOdno]);
  if (id.isNotEmpty) return 'Order reference $id';
  return 'No order created';
}

String safetyLine(Map<String, dynamic> safety) {
  if (safety['dry_run'] == true || safety['runtime_dry_run'] == true) {
    return 'Safety: Dry-run mode';
  }
  if (safety['kill_switch'] == true || safety['kill_switch_enabled'] == true) {
    return 'Safety: Kill switch ON';
  }
  if (safety['market_open'] == false) return 'Safety: Market closed';
  if (safety['kis_real_order_enabled'] == false) {
    return 'Safety: KIS real order disabled';
  }
  if (safety['entry_allowed_now'] == false) {
    return 'Safety: New buy entries are not allowed now';
  }
  return 'Safety: Live KIS ready';
}

String? selectedSymbolMismatch({
  required String selectedSymbol,
  required String? returnedSymbol,
}) {
  final selected = selectedSymbol.trim().toUpperCase();
  final returned = returnedSymbol?.trim().toUpperCase() ?? '';
  if (selected.isEmpty || returned.isEmpty || selected == returned) return null;
  return 'Returned candidate does not match selected symbol. '
      'Selected: $selected, Returned: $returned';
}
