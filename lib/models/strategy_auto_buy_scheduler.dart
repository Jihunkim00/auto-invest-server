class StrategyAutoBuySchedulerStatus {
  const StrategyAutoBuySchedulerStatus({
    required this.provider,
    required this.market,
    required this.enabled,
    required this.dryRunOnly,
    required this.promotionQueueOnly,
    required this.allowLiveOrders,
    required this.realOrderSubmitAllowed,
    required this.allowedProfiles,
    required this.runsToday,
    required this.maxRunsPerDay,
    required this.minMinutesBetweenRuns,
    required this.afterNoNewEntryTime,
    required this.pendingPromotionCount,
    required this.scheduleSlots,
    required this.safety,
    this.activeProfile,
    this.nextAllowedRunAt,
    this.marketOpen,
    this.primaryBlockReason,
    this.latestSchedulerRun,
  });

  final String provider;
  final String market;
  final bool enabled;
  final bool dryRunOnly;
  final bool promotionQueueOnly;
  final bool allowLiveOrders;
  final bool realOrderSubmitAllowed;
  final String? activeProfile;
  final List<String> allowedProfiles;
  final int runsToday;
  final int maxRunsPerDay;
  final DateTime? nextAllowedRunAt;
  final int minMinutesBetweenRuns;
  final bool? marketOpen;
  final bool afterNoNewEntryTime;
  final String? primaryBlockReason;
  final int pendingPromotionCount;
  final Map<String, dynamic>? latestSchedulerRun;
  final List<String> scheduleSlots;
  final Map<String, dynamic> safety;

  factory StrategyAutoBuySchedulerStatus.fromJson(Map<String, dynamic> json) {
    return StrategyAutoBuySchedulerStatus(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      enabled: json['enabled'] == true,
      dryRunOnly: json['dry_run_only'] != false,
      promotionQueueOnly: json['promotion_queue_only'] != false,
      allowLiveOrders: json['allow_live_orders'] == true,
      realOrderSubmitAllowed: json['real_order_submit_allowed'] == true,
      activeProfile: _nullableString(json['active_profile']),
      allowedProfiles: _strings(json['allowed_profiles']),
      runsToday: _int(json['runs_today']),
      maxRunsPerDay: _int(json['max_runs_per_day']),
      nextAllowedRunAt: _dateTime(json['next_allowed_run_at']),
      minMinutesBetweenRuns: _int(json['min_minutes_between_runs']),
      marketOpen: _nullableBool(json['market_open']),
      afterNoNewEntryTime: json['after_no_new_entry_time'] == true,
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      pendingPromotionCount: _int(json['pending_promotion_count']),
      latestSchedulerRun: _nullableMap(json['latest_scheduler_run']),
      scheduleSlots: _strings(json['schedule_slots']),
      safety: _map(json['safety']),
    );
  }

  StrategyAutoBuySchedulerStatus copyWith({
    String? provider,
    String? market,
    bool? enabled,
    bool? dryRunOnly,
    bool? promotionQueueOnly,
    bool? allowLiveOrders,
    bool? realOrderSubmitAllowed,
    String? activeProfile,
    List<String>? allowedProfiles,
    int? runsToday,
    int? maxRunsPerDay,
    DateTime? nextAllowedRunAt,
    int? minMinutesBetweenRuns,
    bool? marketOpen,
    bool? afterNoNewEntryTime,
    String? primaryBlockReason,
    bool clearPrimaryBlockReason = false,
    int? pendingPromotionCount,
    Map<String, dynamic>? latestSchedulerRun,
    List<String>? scheduleSlots,
    Map<String, dynamic>? safety,
  }) {
    return StrategyAutoBuySchedulerStatus(
      provider: provider ?? this.provider,
      market: market ?? this.market,
      enabled: enabled ?? this.enabled,
      dryRunOnly: dryRunOnly ?? this.dryRunOnly,
      promotionQueueOnly: promotionQueueOnly ?? this.promotionQueueOnly,
      allowLiveOrders: allowLiveOrders ?? this.allowLiveOrders,
      realOrderSubmitAllowed:
          realOrderSubmitAllowed ?? this.realOrderSubmitAllowed,
      activeProfile: activeProfile ?? this.activeProfile,
      allowedProfiles: allowedProfiles ?? this.allowedProfiles,
      runsToday: runsToday ?? this.runsToday,
      maxRunsPerDay: maxRunsPerDay ?? this.maxRunsPerDay,
      nextAllowedRunAt: nextAllowedRunAt ?? this.nextAllowedRunAt,
      minMinutesBetweenRuns:
          minMinutesBetweenRuns ?? this.minMinutesBetweenRuns,
      marketOpen: marketOpen ?? this.marketOpen,
      afterNoNewEntryTime: afterNoNewEntryTime ?? this.afterNoNewEntryTime,
      primaryBlockReason: clearPrimaryBlockReason
          ? null
          : primaryBlockReason ?? this.primaryBlockReason,
      pendingPromotionCount:
          pendingPromotionCount ?? this.pendingPromotionCount,
      latestSchedulerRun: latestSchedulerRun ?? this.latestSchedulerRun,
      scheduleSlots: scheduleSlots ?? this.scheduleSlots,
      safety: safety ?? this.safety,
    );
  }
}

class StrategyAutoBuySchedulerRunResult {
  const StrategyAutoBuySchedulerRunResult({
    required this.status,
    required this.action,
    required this.provider,
    required this.market,
    required this.createdPromotion,
    required this.realOrderSubmitted,
    required this.validationCalled,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.safety,
    this.activeProfile,
    this.dryRunResult,
    this.promotion,
    this.blockReason,
    this.schedulerRunId,
  });

  final String status;
  final String action;
  final String provider;
  final String market;
  final String? activeProfile;
  final Map<String, dynamic>? dryRunResult;
  final Map<String, dynamic>? promotion;
  final bool createdPromotion;
  final String? blockReason;
  final int? schedulerRunId;
  final bool realOrderSubmitted;
  final bool validationCalled;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final Map<String, dynamic> safety;

  factory StrategyAutoBuySchedulerRunResult.fromJson(
      Map<String, dynamic> json) {
    return StrategyAutoBuySchedulerRunResult(
      status: _string(json['status'], 'unknown'),
      action: _string(json['action'], 'blocked'),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      dryRunResult: _nullableMap(json['dry_run_result']),
      promotion: _nullableMap(json['promotion']),
      createdPromotion: json['created_promotion'] == true,
      blockReason: _nullableString(json['block_reason']),
      schedulerRunId: _nullableInt(json['scheduler_run_id']),
      realOrderSubmitted: json['real_order_submitted'] == true,
      validationCalled: json['validation_called'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
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

bool? _nullableBool(Object? value) {
  if (value is bool) return value;
  return null;
}

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

Map<String, dynamic>? _nullableMap(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : null;
}

List<String> _strings(Object? value) {
  if (value is! List) return const [];
  return [for (final item in value) item.toString()];
}
