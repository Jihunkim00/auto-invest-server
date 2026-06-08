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

String translateReason(Object? value,
    {num? entryPenalty, bool singleSymbolContext = false}) {
  if (entryPenalty != null && entryPenalty >= 900) {
    return 'Entry blocked by GPT/risk context';
  }
  final text = displayText(value, fallback: '');
  if (text.isEmpty) return 'Not available';
  final parts = text.split(',').map((part) => part.trim()).toList();
  if (parts.length > 1 && parts.every(_looksLikeReasonCode)) {
    return parts
        .map((part) => translateReason(
              part,
              entryPenalty: entryPenalty,
              singleSymbolContext: singleSymbolContext,
            ))
        .join(', ');
  }
  final normalized = text.toLowerCase();
  if (normalized == 'score_threshold_not_met') {
    return 'Score below entry threshold';
  }
  if (normalized == 'sell_pressure_too_high') {
    return 'Sell pressure too high';
  }
  if (normalized == 'buy_sell_spread_too_weak') {
    return 'Buy-sell spread too weak';
  }
  if (normalized == 'missing_indicators') {
    return 'Indicator data unavailable';
  }
  if (normalized == 'after_no_new_entry_time') {
    return 'New buy entries are blocked after 15:00';
  }
  if (normalized == 'near_close') {
    return 'Market is near close';
  }
  if (normalized == 'near_close_no_new_entry') {
    return 'New buy entries are blocked near close';
  }
  if (normalized == 'insufficient_data') {
    return 'KIS OHLCV data was not available';
  }
  if (normalized == 'insufficient_cash' ||
      normalized == 'insufficient_cash_for_min_order') {
    return 'Available cash is below estimated order amount';
  }
  if (normalized == 'hard_blocked') {
    return 'Hard risk block';
  }
  if (normalized == 'market_research_blocked') {
    return 'Market research block';
  }
  if (normalized == 'gpt_hard_block_new_buy') {
    return 'GPT/risk context blocks new buy entries';
  }
  if (normalized == 'kr_trading_disabled') {
    return singleSymbolContext
        ? 'KIS trading is disabled'
        : 'KR preview only / trading disabled';
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
  if (normalized == 'below_ema20') {
    return 'Price below EMA20';
  }
  if (normalized == 'below_ema50') {
    return 'Price below EMA50';
  }
  if (normalized == 'below_vwap') {
    return 'Price below VWAP';
  }
  if (normalized == 'above_ema20') {
    return 'Price above EMA20';
  }
  if (normalized == 'above_ema50') {
    return 'Price above EMA50';
  }
  if (normalized == 'above_vwap') {
    return 'Price above VWAP';
  }
  if (normalized == 'overbought_rsi') {
    return 'RSI overbought';
  }
  if (normalized == 'oversold_rsi') {
    return 'RSI oversold';
  }
  if (normalized == 'negative_momentum') {
    return 'Momentum negative';
  }
  if (normalized == 'weak_recent_return') {
    return 'Recent return weak';
  }
  if (normalized == 'possible_mean_reversion_only') {
    return 'Possible mean reversion only';
  }
  if (normalized == 'chase_risk') {
    return 'Overbought setup: chase risk';
  }
  if (normalized == 'kill_switch_enabled') {
    return 'Kill switch is ON';
  }
  if (normalized == 'confirm_live_required') {
    return 'Confirm live order before submitting';
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

bool _looksLikeReasonCode(String value) {
  if (value.isEmpty) return false;
  return RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(value);
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
