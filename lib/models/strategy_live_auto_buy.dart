class StrategyLiveAutoBuyReadiness {
  const StrategyLiveAutoBuyReadiness({
    required this.enabled,
    required this.ready,
    required this.provider,
    required this.market,
    required this.dryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.schedulerLiveEnabled,
    required this.recentDryRunRequired,
    required this.recentDryRunFound,
    required this.recentDryRunTtlMinutes,
    required this.maxOrdersPerDay,
    required this.ordersUsedToday,
    required this.ordersRemainingToday,
    required this.maxNotionalKrw,
    required this.maxNotionalPct,
    required this.checks,
    required this.riskFlags,
    required this.gatingNotes,
    required this.safety,
    this.activeProfile,
    this.allowedProfiles = const [],
    this.recentDryRunAgeMinutes,
    this.selectedSymbol,
    this.primaryBlockReason,
  });

  final bool enabled;
  final bool ready;
  final String provider;
  final String market;
  final String? activeProfile;
  final List<String> allowedProfiles;
  final bool dryRun;
  final bool killSwitch;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final bool schedulerLiveEnabled;
  final bool recentDryRunRequired;
  final bool recentDryRunFound;
  final double? recentDryRunAgeMinutes;
  final int recentDryRunTtlMinutes;
  final String? selectedSymbol;
  final int maxOrdersPerDay;
  final int ordersUsedToday;
  final int ordersRemainingToday;
  final double maxNotionalKrw;
  final double maxNotionalPct;
  final String? primaryBlockReason;
  final List<Map<String, dynamic>> checks;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> safety;

  factory StrategyLiveAutoBuyReadiness.fromJson(Map<String, dynamic> json) {
    return StrategyLiveAutoBuyReadiness(
      enabled: json['enabled'] == true,
      ready: json['ready'] == true,
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      allowedProfiles: _strings(json['allowed_profiles']),
      dryRun: json['dry_run'] == true,
      killSwitch: json['kill_switch'] == true,
      kisEnabled: json['kis_enabled'] == true,
      kisRealOrderEnabled: json['kis_real_order_enabled'] == true,
      schedulerLiveEnabled: json['scheduler_live_enabled'] == true,
      recentDryRunRequired: json['recent_dry_run_required'] == true,
      recentDryRunFound: json['recent_dry_run_found'] == true,
      recentDryRunAgeMinutes:
          _nullableDouble(json['recent_dry_run_age_minutes']),
      recentDryRunTtlMinutes: _int(json['recent_dry_run_ttl_minutes']),
      selectedSymbol: _nullableString(json['selected_symbol']),
      maxOrdersPerDay: _int(json['max_orders_per_day']),
      ordersUsedToday: _int(json['orders_used_today']),
      ordersRemainingToday: _int(json['orders_remaining_today']),
      maxNotionalKrw: _double(json['max_notional_krw']),
      maxNotionalPct: _double(json['max_notional_pct']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      checks: _maps(json['checks']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      safety: _map(json['safety']),
    );
  }
}

class StrategyLiveAutoBuyPreflightChecklistItem {
  const StrategyLiveAutoBuyPreflightChecklistItem({
    required this.key,
    required this.status,
    this.labelKey,
    this.displayLabel,
    this.detail,
    this.blocking = false,
  });

  final String key;
  final String status;
  final String? labelKey;
  final String? displayLabel;
  final String? detail;
  final bool blocking;

  bool get passed => status == 'pass';
  bool get warning => status == 'warn';
  bool get failed => status == 'fail';

  factory StrategyLiveAutoBuyPreflightChecklistItem.fromJson(Object? value) {
    if (value is Map) {
      final json = Map<String, dynamic>.from(value);
      return StrategyLiveAutoBuyPreflightChecklistItem(
        key: _string(json['key'], 'check'),
        status: _string(json['status'], 'warn'),
        labelKey: _nullableString(json['label_key']),
        displayLabel: _nullableString(json['display_label']),
        detail: _nullableString(json['detail']),
        blocking: json['blocking'] == true,
      );
    }
    return StrategyLiveAutoBuyPreflightChecklistItem(
      key: 'check',
      status: 'warn',
      detail: _nullableString(value),
    );
  }
}

class StrategyLiveAutoBuyPreflightResult {
  const StrategyLiveAutoBuyPreflightResult({
    required this.provider,
    required this.market,
    required this.preflightStatus,
    required this.canSubmitAfterConfirmation,
    required this.finalConfirmationRequired,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.promotionStateAllowed,
    required this.staleOrExpired,
    required this.dryRun,
    required this.killSwitch,
    required this.kisRealOrderEnabled,
    required this.liveAutoBuyEnabled,
    required this.scoreSummary,
    required this.riskFlags,
    required this.gatingNotes,
    required this.checklist,
    required this.nextRequiredAction,
    required this.safety,
    this.promotionId,
    this.symbol,
    this.orderId,
    this.brokerOrderId,
    this.promotionStatus,
    this.reviewStatus,
    this.promotionStateBlockReason,
    this.marketSessionAllowed,
    this.marketSessionBlockReason,
    this.activeProfileName,
    this.proposedNotionalKrw,
    this.maxNotionalKrw,
    this.availableCashKrw,
    this.estimatedQuantity,
    this.primaryBlockReason,
  });

  final int? promotionId;
  final String? symbol;
  final String provider;
  final String market;
  final String preflightStatus;
  final bool canSubmitAfterConfirmation;
  final bool finalConfirmationRequired;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final int? orderId;
  final String? brokerOrderId;
  final String? promotionStatus;
  final String? reviewStatus;
  final bool promotionStateAllowed;
  final String? promotionStateBlockReason;
  final bool staleOrExpired;
  final bool? marketSessionAllowed;
  final String? marketSessionBlockReason;
  final bool dryRun;
  final bool killSwitch;
  final bool kisRealOrderEnabled;
  final bool liveAutoBuyEnabled;
  final String? activeProfileName;
  final Map<String, dynamic> scoreSummary;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final double? proposedNotionalKrw;
  final double? maxNotionalKrw;
  final double? availableCashKrw;
  final int? estimatedQuantity;
  final List<StrategyLiveAutoBuyPreflightChecklistItem> checklist;
  final String? primaryBlockReason;
  final String nextRequiredAction;
  final Map<String, dynamic> safety;

  bool get isAllowed => preflightStatus == 'allowed';
  bool get isBlocked => preflightStatus == 'blocked';
  bool get requiresReview => preflightStatus == 'review_required';
  bool get isReadOnly =>
      realOrderSubmitted == false &&
      brokerSubmitCalled == false &&
      manualSubmitCalled == false &&
      safety['read_only'] == true;

  factory StrategyLiveAutoBuyPreflightResult.fromJson(
      Map<String, dynamic> json) {
    return StrategyLiveAutoBuyPreflightResult(
      promotionId: _nullableInt(json['promotion_id']),
      symbol: _nullableString(json['symbol']),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      preflightStatus: _string(json['preflight_status'], 'blocked'),
      canSubmitAfterConfirmation: json['can_submit_after_confirmation'] == true,
      finalConfirmationRequired: json['final_confirmation_required'] != false,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      orderId: _nullableInt(json['order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      promotionStatus: _nullableString(json['promotion_status']),
      reviewStatus: _nullableString(json['review_status']),
      promotionStateAllowed: json['promotion_state_allowed'] == true,
      promotionStateBlockReason:
          _nullableString(json['promotion_state_block_reason']),
      staleOrExpired: json['stale_or_expired'] == true,
      marketSessionAllowed: json.containsKey('market_session_allowed')
          ? json['market_session_allowed'] == true
          : null,
      marketSessionBlockReason:
          _nullableString(json['market_session_block_reason']),
      dryRun: json['dry_run'] == true,
      killSwitch: json['kill_switch'] == true,
      kisRealOrderEnabled: json['kis_real_order_enabled'] == true,
      liveAutoBuyEnabled: json['live_auto_buy_enabled'] == true,
      activeProfileName: _nullableString(json['active_profile_name']),
      scoreSummary: _map(json['score_summary']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      proposedNotionalKrw: _nullableDouble(json['proposed_notional_krw']),
      maxNotionalKrw: _nullableDouble(json['max_notional_krw']),
      availableCashKrw: _nullableDouble(json['available_cash_krw']),
      estimatedQuantity: _nullableInt(json['estimated_quantity']),
      checklist: _preflightChecklist(json['checklist']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      nextRequiredAction:
          _string(json['next_required_action'], 'resolve_block'),
      safety: _map(json['safety']),
    );
  }
}

class StrategyLiveAutoBuyRunResult {
  const StrategyLiveAutoBuyRunResult({
    required this.status,
    required this.action,
    required this.provider,
    required this.market,
    required this.targetRiskApproved,
    required this.validationApproved,
    required this.submitted,
    required this.riskFlags,
    required this.gatingNotes,
    required this.safety,
    this.activeProfile,
    this.symbol,
    this.symbolName,
    this.sourceDryRunId,
    this.sourceSignalId,
    this.sourceTradeRunId,
    this.promotionId,
    this.promotionTrace = const {},
    this.quantity,
    this.estimatedPrice,
    this.submittedNotionalKrw,
    this.relatedOrderId,
    this.brokerOrderId,
    this.brokerStatus,
    this.internalStatus,
    this.blockReason,
    this.attemptId,
    this.signalId,
    this.tradeRunId,
    this.createdAt,
  });

  final String status;
  final String action;
  final String provider;
  final String market;
  final String? activeProfile;
  final String? symbol;
  final String? symbolName;
  final int? sourceDryRunId;
  final int? sourceSignalId;
  final int? sourceTradeRunId;
  final int? promotionId;
  final Map<String, dynamic> promotionTrace;
  final bool targetRiskApproved;
  final bool validationApproved;
  final bool submitted;
  final int? quantity;
  final double? estimatedPrice;
  final double? submittedNotionalKrw;
  final int? relatedOrderId;
  final String? brokerOrderId;
  final String? brokerStatus;
  final String? internalStatus;
  final String? blockReason;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final int? attemptId;
  final int? signalId;
  final int? tradeRunId;
  final DateTime? createdAt;
  final Map<String, dynamic> safety;

  bool get blocked => action == 'blocked' || blockReason != null;
  bool get syncRequired => status == 'sync_required';

  factory StrategyLiveAutoBuyRunResult.fromJson(Map<String, dynamic> json) {
    return StrategyLiveAutoBuyRunResult(
      status: _string(json['status'], 'blocked'),
      action: _string(json['action'], 'blocked'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      symbol: _nullableString(json['symbol']),
      symbolName: _nullableString(json['symbol_name']),
      sourceDryRunId: _nullableInt(json['source_dry_run_id']),
      sourceSignalId: _nullableInt(json['source_signal_id']),
      sourceTradeRunId: _nullableInt(json['source_trade_run_id']),
      promotionId: _nullableInt(json['promotion_id']),
      promotionTrace: _map(json['promotion_trace']),
      targetRiskApproved: json['target_risk_approved'] == true,
      validationApproved: json['validation_approved'] == true,
      submitted: json['submitted'] == true,
      quantity: _nullableInt(json['quantity']),
      estimatedPrice: _nullableDouble(json['estimated_price']),
      submittedNotionalKrw: _nullableDouble(json['submitted_notional_krw']),
      relatedOrderId: _nullableInt(json['related_order_id']),
      brokerOrderId: _nullableString(json['broker_order_id']),
      brokerStatus: _nullableString(json['broker_status']),
      internalStatus: _nullableString(json['internal_status']),
      blockReason: _nullableString(json['block_reason']),
      riskFlags: _strings(json['risk_flags']),
      gatingNotes: _strings(json['gating_notes']),
      attemptId: _nullableInt(json['attempt_id']),
      signalId: _nullableInt(json['signal_id']),
      tradeRunId: _nullableInt(json['trade_run_id']),
      createdAt: _dateTime(json['created_at']),
      safety: _map(json['safety']),
    );
  }
}

class StrategyLiveAutoBuyRecent {
  const StrategyLiveAutoBuyRecent({
    required this.provider,
    required this.market,
    required this.items,
    required this.safety,
  });

  final String provider;
  final String market;
  final List<StrategyLiveAutoBuyRunResult> items;
  final Map<String, dynamic> safety;

  StrategyLiveAutoBuyRunResult? get latest =>
      items.isEmpty ? null : items.first;

  factory StrategyLiveAutoBuyRecent.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'];
    return StrategyLiveAutoBuyRecent(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      items: rawItems is List
          ? [
              for (final item in rawItems)
                if (item is Map)
                  StrategyLiveAutoBuyRunResult.fromJson(
                    Map<String, dynamic>.from(item),
                  ),
            ]
          : const [],
      safety: _map(json['safety']),
    );
  }
}

String _string(Object? value, String fallback) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty || text == 'null' ? null : text;
}

double _double(Object? value) => _nullableDouble(value) ?? 0;

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString().replaceAll(',', '').trim());
}

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
}

List<StrategyLiveAutoBuyPreflightChecklistItem> _preflightChecklist(
    Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      StrategyLiveAutoBuyPreflightChecklistItem.fromJson(item),
  ];
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? null : DateTime.tryParse(text);
}
