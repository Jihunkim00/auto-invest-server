class KisLimitedAutoBuy {
  const KisLimitedAutoBuy({
    required this.status,
    required this.mode,
    required this.result,
    required this.action,
    required this.reason,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.validationCalled,
    required this.autoBuyEnabled,
    required this.liveAutoBuyEnabled,
    required this.limitedAutoBuyEnabled,
    required this.buyReadinessEnabled,
    required this.schedulerRealOrdersEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.kisRealOrderEnabled,
    required this.marketOpen,
    required this.entryAllowedNow,
    required this.realOrderSubmitAllowed,
    required this.checks,
    required this.safety,
    required this.auditMetadata,
    required this.rawPayload,
    this.primaryBlockReason,
    this.humanReadableStatus,
    this.noNewEntryAfter,
    this.cashAvailable,
    this.dailyBuyCount,
    this.dailyBuyLimit,
    this.dailyBuyLimitRemaining,
    this.maxNotionalPct,
    this.estimatedMaxNotional,
    this.symbol,
    this.quantity,
    this.notional,
    this.finalScore,
    this.finalBuyScore,
    this.finalSellScore,
    this.confidence,
    this.requiredBuyScore,
    this.buySellSpread,
    this.orderId,
    this.brokerOrderId,
    this.kisOdno,
    this.createdAt,
    this.blockedBy = const [],
    this.failedChecks = const [],
    this.blockReasons = const [],
    this.candidates = const [],
    this.finalCandidate,
  });

  factory KisLimitedAutoBuy.fromJson(Map<String, dynamic> json) {
    final safety = _dynamicMap(json['safety']);
    final checks = _dynamicMap(json['checks']);
    final finalCandidateMap = _dynamicMap(json['final_candidate']);
    return KisLimitedAutoBuy(
      status: _stringValue(json['status'], fallback: 'ok'),
      mode: _stringValue(json['mode'], fallback: 'kis_limited_auto_buy_run'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      reason: _stringValue(json['reason'], fallback: ''),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      humanReadableStatus: _nullableString(json['human_readable_status']),
      symbol: _nullableString(json['symbol']),
      quantity: _nullableInt(json['quantity'] ?? json['qty']),
      notional: _nullableDouble(json['estimated_notional'] ?? json['notional']),
      finalScore:
          _nullableDouble(json['final_score'] ?? json['final_buy_score']),
      finalBuyScore:
          _nullableDouble(json['final_buy_score'] ?? json['final_score']),
      finalSellScore: _nullableDouble(json['final_sell_score']),
      confidence: _nullableDouble(json['confidence']),
      requiredBuyScore: _nullableDouble(
          json['required_buy_score'] ?? json['effective_min_entry_score']),
      buySellSpread: _nullableDouble(json['buy_sell_spread']),
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      kisOdno: _nullableString(json['kis_odno']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      validationCalled: _boolValue(json['validation_called']) ?? false,
      autoBuyEnabled: _boolValue(json['auto_buy_enabled'] ??
              safety['auto_buy_enabled'] ??
              safety['auto_buy_execution_enabled']) ??
          false,
      liveAutoBuyEnabled: _boolValue(json['live_auto_buy_enabled'] ??
              safety['live_auto_buy_enabled'] ??
              checks['kis_live_auto_buy_enabled']) ??
          false,
      limitedAutoBuyEnabled: _boolValue(json['limited_auto_buy_enabled'] ??
              safety['limited_auto_buy_enabled'] ??
              checks['kis_limited_auto_buy_enabled']) ??
          false,
      buyReadinessEnabled: _boolValue(json['buy_readiness_enabled'] ??
              safety['buy_readiness_enabled'] ??
              checks['kis_limited_auto_buy_readiness_enabled']) ??
          false,
      schedulerRealOrdersEnabled: _boolValue(
              json['scheduler_real_orders_enabled'] ??
                  json['scheduler_real_order_enabled'] ??
                  safety['scheduler_real_orders_enabled'] ??
                  safety['scheduler_real_order_enabled']) ??
          false,
      dryRun: _boolValue(
              json['dry_run'] ?? safety['dry_run'] ?? checks['dry_run']) ??
          true,
      killSwitch: _boolValue(json['kill_switch'] ??
              safety['kill_switch'] ??
              checks['kill_switch']) ??
          false,
      kisRealOrderEnabled: _boolValue(json['kis_real_order_enabled'] ??
              safety['kis_real_order_enabled'] ??
              checks['kis_real_order_enabled']) ??
          false,
      marketOpen:
          _boolValue(json['market_open'] ?? checks['market_open']) ?? false,
      entryAllowedNow: _boolValue(
              json['entry_allowed_now'] ?? checks['entry_allowed_now']) ??
          false,
      noNewEntryAfter: _nullableString(
          json['no_new_entry_after'] ?? checks['no_new_entry_after']),
      cashAvailable:
          _nullableDouble(json['cash_available'] ?? checks['cash_available']),
      dailyBuyCount: _nullableInt(json['daily_buy_count']),
      dailyBuyLimit: _nullableInt(json['daily_buy_limit']),
      dailyBuyLimitRemaining: _nullableInt(json['daily_buy_limit_remaining']),
      maxNotionalPct: _nullableDouble(
          json['max_notional_pct'] ?? safety['max_notional_pct']),
      estimatedMaxNotional: _nullableDouble(json['estimated_max_notional']),
      realOrderSubmitAllowed: _boolValue(json['real_order_submit_allowed'] ??
              safety['real_order_submit_allowed']) ??
          false,
      checks: checks,
      safety: safety,
      auditMetadata: _dynamicMap(json['audit_metadata']),
      rawPayload: _dynamicMap(json),
      createdAt: _nullableString(json['created_at']),
      blockedBy: _stringList(json['blocked_by']),
      failedChecks: _stringList(json['failed_checks']),
      blockReasons: _stringList(json['block_reasons']),
      candidates: _candidateList(json['candidates']),
      finalCandidate: finalCandidateMap.isEmpty
          ? null
          : KisLimitedAutoBuyCandidate.fromJson(finalCandidateMap),
    );
  }

  final String status;
  final String mode;
  final String result;
  final String action;
  final String reason;
  final String? primaryBlockReason;
  final String? humanReadableStatus;
  final String? symbol;
  final int? quantity;
  final double? notional;
  final double? finalScore;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final double? requiredBuyScore;
  final double? buySellSpread;
  final int? orderId;
  final String? brokerOrderId;
  final String? kisOdno;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool validationCalled;
  final bool autoBuyEnabled;
  final bool liveAutoBuyEnabled;
  final bool limitedAutoBuyEnabled;
  final bool buyReadinessEnabled;
  final bool schedulerRealOrdersEnabled;
  final bool dryRun;
  final bool killSwitch;
  final bool kisRealOrderEnabled;
  final bool marketOpen;
  final bool entryAllowedNow;
  final String? noNewEntryAfter;
  final double? cashAvailable;
  final int? dailyBuyCount;
  final int? dailyBuyLimit;
  final int? dailyBuyLimitRemaining;
  final double? maxNotionalPct;
  final double? estimatedMaxNotional;
  final bool realOrderSubmitAllowed;
  final Map<String, dynamic> checks;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> auditMetadata;
  final Map<String, dynamic> rawPayload;
  final String? createdAt;
  final List<String> blockedBy;
  final List<String> failedChecks;
  final List<String> blockReasons;
  final List<KisLimitedAutoBuyCandidate> candidates;
  final KisLimitedAutoBuyCandidate? finalCandidate;

  bool get submitted => realOrderSubmitted || result == 'submitted';

  bool get buyReady =>
      action == 'buy_ready' ||
      result == 'ready' ||
      result == 'readiness_only' ||
      finalCandidate?.entryReady == true;

  bool check(String key) => _boolValue(checks[key]) ?? false;

  bool? nullableCheck(String key) => _boolValue(checks[key]);

  int? safetyInt(String key) => _nullableInt(safety[key]);

  double? safetyDouble(String key) => _nullableDouble(safety[key]);

  bool safetyFlag(String key) => _boolValue(safety[key]) ?? false;
}

class KisLimitedAutoBuyCandidate {
  const KisLimitedAutoBuyCandidate({
    required this.symbol,
    required this.status,
    required this.tradeAllowed,
    required this.buyReadinessOnly,
    required this.buyActionable,
    required this.entryReady,
    required this.duplicatePosition,
    required this.duplicateOpenOrder,
    required this.cashSufficient,
    required this.marketSessionAllowed,
    required this.noNewEntryAfterBlocked,
    required this.riskFlags,
    required this.gatingNotes,
    required this.blockReasons,
    required this.technicalSnapshot,
    required this.rawPayload,
    this.companyName,
    this.currentPrice,
    this.availableCash,
    this.estimatedNotional,
    this.suggestedQuantity,
    this.maxNotionalPct,
    this.finalBuyScore,
    this.finalSellScore,
    this.quantBuyScore,
    this.quantSellScore,
    this.aiBuyScore,
    this.aiSellScore,
    this.gptBuyScore,
    this.gptSellScore,
    this.confidence,
    this.gateLevel,
    this.requiredBuyScore,
    this.effectiveMinEntryScore,
    this.buySellSpread,
    this.indicatorStatus,
    this.indicatorBarCount,
    this.dailyBuyLimitRemaining,
    this.gptReason,
  });

  factory KisLimitedAutoBuyCandidate.fromJson(Map<String, dynamic> json) {
    return KisLimitedAutoBuyCandidate(
      symbol: _stringValue(json['symbol'], fallback: 'n/a'),
      companyName: _nullableString(
          json['company_name'] ?? json['company'] ?? json['name']),
      currentPrice: _nullableDouble(json['current_price']),
      availableCash:
          _nullableDouble(json['available_cash'] ?? json['cash_available']),
      estimatedNotional: _nullableDouble(
          json['estimated_notional'] ?? json['suggested_notional']),
      suggestedQuantity:
          _nullableInt(json['suggested_quantity'] ?? json['quantity']),
      maxNotionalPct: _nullableDouble(json['max_notional_pct']),
      finalBuyScore:
          _nullableDouble(json['final_buy_score'] ?? json['final_score']),
      finalSellScore: _nullableDouble(json['final_sell_score']),
      quantBuyScore:
          _nullableDouble(json['quant_buy_score'] ?? json['quant_score']),
      quantSellScore: _nullableDouble(json['quant_sell_score']),
      aiBuyScore:
          _nullableDouble(json['ai_buy_score'] ?? json['gpt_buy_score']),
      aiSellScore:
          _nullableDouble(json['ai_sell_score'] ?? json['gpt_sell_score']),
      gptBuyScore:
          _nullableDouble(json['gpt_buy_score'] ?? json['ai_buy_score']),
      gptSellScore:
          _nullableDouble(json['gpt_sell_score'] ?? json['ai_sell_score']),
      confidence: _nullableDouble(json['confidence']),
      gateLevel: _nullableInt(json['gate_level']),
      requiredBuyScore: _nullableDouble(json['required_buy_score']),
      effectiveMinEntryScore:
          _nullableDouble(json['effective_min_entry_score']),
      buySellSpread: _nullableDouble(json['buy_sell_spread']),
      indicatorStatus: _nullableString(json['indicator_status']),
      indicatorBarCount: _nullableInt(json['indicator_bar_count']),
      status: _stringValue(json['status'], fallback: 'HOLD'),
      tradeAllowed: _boolValue(json['trade_allowed']) ?? false,
      buyReadinessOnly: _boolValue(json['buy_readiness_only']) ?? true,
      buyActionable: _boolValue(json['buy_actionable']) ?? false,
      entryReady: _boolValue(json['entry_ready']) ?? false,
      duplicatePosition: _boolValue(json['duplicate_position']) ?? false,
      duplicateOpenOrder: _boolValue(json['duplicate_open_buy_order'] ??
              json['duplicate_open_order']) ??
          false,
      cashSufficient: _boolValue(json['cash_sufficient']) ?? false,
      marketSessionAllowed: _boolValue(json['market_session_allowed']) ?? false,
      noNewEntryAfterBlocked:
          _boolValue(json['no_new_entry_after_blocked']) ?? false,
      dailyBuyLimitRemaining: _nullableInt(json['daily_buy_limit_remaining']),
      riskFlags: _stringList(json['risk_flags']),
      gatingNotes: _stringList(json['gating_notes']),
      blockReasons: _stringList(json['block_reasons']),
      gptReason: _nullableString(json['gpt_reason']),
      technicalSnapshot: _dynamicMap(json['technical_snapshot']),
      rawPayload: _dynamicMap(json),
    );
  }

  final String symbol;
  final String? companyName;
  final double? currentPrice;
  final double? availableCash;
  final double? estimatedNotional;
  final int? suggestedQuantity;
  final double? maxNotionalPct;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? gptBuyScore;
  final double? gptSellScore;
  final double? confidence;
  final int? gateLevel;
  final double? requiredBuyScore;
  final double? effectiveMinEntryScore;
  final double? buySellSpread;
  final String? indicatorStatus;
  final int? indicatorBarCount;
  final String status;
  final bool tradeAllowed;
  final bool buyReadinessOnly;
  final bool buyActionable;
  final bool entryReady;
  final bool duplicatePosition;
  final bool duplicateOpenOrder;
  final bool cashSufficient;
  final bool marketSessionAllowed;
  final bool noNewEntryAfterBlocked;
  final int? dailyBuyLimitRemaining;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final List<String> blockReasons;
  final String? gptReason;
  final Map<String, dynamic> technicalSnapshot;
  final Map<String, dynamic> rawPayload;
}

List<KisLimitedAutoBuyCandidate> _candidateList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisLimitedAutoBuyCandidate.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}

Map<String, dynamic> _dynamicMap(Object? value) {
  if (value is Map<String, dynamic>) return value;
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _stringValue(Object? value, {required String fallback}) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  final text = value.toString().trim();
  if (text.isEmpty || text == 'null') return null;
  return int.tryParse(text);
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}

bool? _boolValue(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
