class KisSchedulerReadiness {
  const KisSchedulerReadiness({
    required this.provider,
    required this.market,
    required this.mode,
    required this.readinessOnly,
    required this.schedulerRealOrdersEnabled,
    required this.realOrderSubmitAllowed,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.summary,
    required this.schedule,
    required this.modules,
    required this.safety,
    required this.recentRuns,
    required this.diagnostics,
    required this.rawPayload,
    this.blockReasons = const [],
  });

  factory KisSchedulerReadiness.fromJson(Map<String, dynamic> json) {
    final summary = KisSchedulerReadinessSummary.fromJson(
      _dynamicMap(json['summary']),
    );
    final safety = _dynamicMap(json['safety']);
    return KisSchedulerReadiness(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(json['mode'], fallback: 'kis_scheduler_readiness'),
      readinessOnly: _boolValue(json['readiness_only']) ?? true,
      schedulerRealOrdersEnabled:
          _boolValue(json['scheduler_real_orders_enabled']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      realOrderSubmitted: _boolValue(
              json['real_order_submitted'] ?? safety['real_order_submitted']) ??
          false,
      brokerSubmitCalled: _boolValue(
              json['broker_submit_called'] ?? safety['broker_submit_called']) ??
          false,
      manualSubmitCalled: _boolValue(
              json['manual_submit_called'] ?? safety['manual_submit_called']) ??
          false,
      summary: summary,
      schedule: _scheduleList(json['schedule']),
      modules: KisSchedulerReadinessModules.fromJson(
        _dynamicMap(json['modules']),
      ),
      safety: safety,
      recentRuns: _recentRunList(json['recent_runs']),
      diagnostics: _dynamicMap(json['diagnostics']),
      blockReasons: _stringList(json['block_reasons']),
      rawPayload: _dynamicMap(json),
    );
  }

  factory KisSchedulerReadiness.safeDefault() {
    return KisSchedulerReadiness.fromJson(const {
      'provider': 'kis',
      'market': 'KR',
      'mode': 'kis_scheduler_readiness',
      'readiness_only': true,
      'scheduler_real_orders_enabled': false,
      'real_order_submit_allowed': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'summary': {
        'scheduler_enabled': false,
        'kis_scheduler_enabled': false,
        'kis_scheduler_dry_run': true,
        'kis_scheduler_allow_real_orders': false,
        'scheduler_real_orders_enabled': false,
        'market_open': false,
        'entry_allowed_now': false,
        'sell_session_allowed': false,
        'real_order_submit_allowed': false,
        'readiness_status': 'DISABLED',
        'primary_block_reason': 'not_loaded',
        'block_reasons': ['not_loaded'],
      },
      'schedule': [],
      'modules': {},
      'safety': {
        'readiness_only': true,
        'scheduler_real_orders_enabled': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      },
      'recent_runs': [],
      'diagnostics': {},
      'block_reasons': ['not_loaded'],
    });
  }

  final String provider;
  final String market;
  final String mode;
  final bool readinessOnly;
  final bool schedulerRealOrdersEnabled;
  final bool realOrderSubmitAllowed;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final KisSchedulerReadinessSummary summary;
  final List<KisSchedulerScheduleItem> schedule;
  final KisSchedulerReadinessModules modules;
  final Map<String, dynamic> safety;
  final List<KisSchedulerRecentRun> recentRuns;
  final Map<String, dynamic> diagnostics;
  final List<String> blockReasons;
  final Map<String, dynamic> rawPayload;
}

class KisSchedulerReadinessSummary {
  const KisSchedulerReadinessSummary({
    required this.schedulerEnabled,
    required this.kisSchedulerEnabled,
    required this.kisSchedulerDryRun,
    required this.kisSchedulerAllowRealOrders,
    required this.schedulerRealOrdersEnabled,
    required this.marketOpen,
    required this.entryAllowedNow,
    required this.sellSessionAllowed,
    required this.realOrderSubmitAllowed,
    required this.readinessStatus,
    this.nextScheduledSlot,
    this.currentSlotLabel,
    this.primaryBlockReason,
    this.blockReasons = const [],
  });

  factory KisSchedulerReadinessSummary.fromJson(Map<String, dynamic> json) {
    final nextSlot = _dynamicMap(json['next_scheduled_slot']);
    return KisSchedulerReadinessSummary(
      schedulerEnabled: _boolValue(json['scheduler_enabled']) ?? false,
      kisSchedulerEnabled: _boolValue(json['kis_scheduler_enabled']) ?? false,
      kisSchedulerDryRun: _boolValue(json['kis_scheduler_dry_run']) ?? true,
      kisSchedulerAllowRealOrders:
          _boolValue(json['kis_scheduler_allow_real_orders']) ?? false,
      schedulerRealOrdersEnabled:
          _boolValue(json['scheduler_real_orders_enabled']) ?? false,
      marketOpen: _boolValue(json['market_open']) ?? false,
      entryAllowedNow: _boolValue(json['entry_allowed_now']) ?? false,
      sellSessionAllowed: _boolValue(json['sell_session_allowed']) ?? false,
      realOrderSubmitAllowed:
          _boolValue(json['real_order_submit_allowed']) ?? false,
      readinessStatus:
          _stringValue(json['readiness_status'], fallback: 'DISABLED'),
      nextScheduledSlot:
          nextSlot.isEmpty ? null : KisSchedulerScheduleItem.fromJson(nextSlot),
      currentSlotLabel: _nullableString(json['current_slot_label']),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
    );
  }

  final bool schedulerEnabled;
  final bool kisSchedulerEnabled;
  final bool kisSchedulerDryRun;
  final bool kisSchedulerAllowRealOrders;
  final bool schedulerRealOrdersEnabled;
  final bool marketOpen;
  final bool entryAllowedNow;
  final bool sellSessionAllowed;
  final bool realOrderSubmitAllowed;
  final String readinessStatus;
  final KisSchedulerScheduleItem? nextScheduledSlot;
  final String? currentSlotLabel;
  final String? primaryBlockReason;
  final List<String> blockReasons;
}

class KisSchedulerScheduleItem {
  const KisSchedulerScheduleItem({
    required this.slotId,
    required this.label,
    required this.scheduledTime,
    required this.timezone,
    required this.purpose,
    required this.enabled,
    required this.realOrderAllowed,
    required this.dryRunOnly,
    this.notes = const [],
  });

  factory KisSchedulerScheduleItem.fromJson(Map<String, dynamic> json) {
    final slotId = _stringValue(
      json['slot_id'] ?? json['label'],
      fallback: 'slot',
    );
    return KisSchedulerScheduleItem(
      slotId: slotId,
      label: _stringValue(json['label'] ?? json['slot_id'], fallback: slotId),
      scheduledTime: _nullableString(json['scheduled_time']) ?? 'n/a',
      timezone: _stringValue(json['timezone'], fallback: 'Asia/Seoul'),
      purpose: _stringValue(json['purpose'], fallback: 'buy_readiness'),
      enabled: _boolValue(json['enabled']) ?? false,
      realOrderAllowed: _boolValue(json['real_order_allowed']) ?? false,
      dryRunOnly: _boolValue(json['dry_run_only']) ?? true,
      notes: _stringList(json['notes']),
    );
  }

  final String slotId;
  final String label;
  final String scheduledTime;
  final String timezone;
  final String purpose;
  final bool enabled;
  final bool realOrderAllowed;
  final bool dryRunOnly;
  final List<String> notes;

  String get displayLabel => label.isEmpty ? slotId : label;
}

class KisSchedulerReadinessModules {
  const KisSchedulerReadinessModules({
    required this.limitedAutoSell,
    required this.limitedAutoBuy,
    required this.portfolioPositionManagement,
    required this.executionReview,
  });

  factory KisSchedulerReadinessModules.fromJson(Map<String, dynamic> json) {
    return KisSchedulerReadinessModules(
      limitedAutoSell: KisSchedulerModuleStatus.fromJson(
        _dynamicMap(json['limited_auto_sell']),
      ),
      limitedAutoBuy: KisSchedulerModuleStatus.fromJson(
        _dynamicMap(json['limited_auto_buy']),
      ),
      portfolioPositionManagement: KisSchedulerModuleStatus.fromJson(
        _dynamicMap(json['portfolio_position_management']),
      ),
      executionReview: KisSchedulerModuleStatus.fromJson(
        _dynamicMap(json['execution_review']),
      ),
    );
  }

  final KisSchedulerModuleStatus limitedAutoSell;
  final KisSchedulerModuleStatus limitedAutoBuy;
  final KisSchedulerModuleStatus portfolioPositionManagement;
  final KisSchedulerModuleStatus executionReview;
}

class KisSchedulerModuleStatus {
  const KisSchedulerModuleStatus({
    required this.available,
    required this.statusEndpoint,
    required this.readyForSchedulerDryRun,
    required this.readyForSchedulerRealOrder,
    required this.rawPayload,
    this.readOnly = false,
    this.stopLossExecutionEnabled = false,
    this.takeProfitExecutionEnabled = false,
    this.liveAutoSellEnabled = false,
    this.autoBuyExecutionEnabled = false,
    this.liveAutoBuyEnabled = false,
    this.dryRun = true,
    this.dailyLimitRemaining,
    this.blockReasons = const [],
  });

  factory KisSchedulerModuleStatus.fromJson(Map<String, dynamic> json) {
    return KisSchedulerModuleStatus(
      available: _boolValue(json['available']) ?? false,
      statusEndpoint: _stringValue(json['status_endpoint'], fallback: ''),
      readOnly: _boolValue(json['read_only']) ?? false,
      stopLossExecutionEnabled:
          _boolValue(json['stop_loss_execution_enabled']) ?? false,
      takeProfitExecutionEnabled:
          _boolValue(json['take_profit_execution_enabled']) ?? false,
      liveAutoSellEnabled: _boolValue(json['live_auto_sell_enabled']) ?? false,
      autoBuyExecutionEnabled:
          _boolValue(json['auto_buy_execution_enabled']) ?? false,
      liveAutoBuyEnabled: _boolValue(json['live_auto_buy_enabled']) ?? false,
      dryRun: _boolValue(json['dry_run']) ?? true,
      dailyLimitRemaining: _nullableInt(json['daily_limit_remaining']),
      readyForSchedulerDryRun:
          _boolValue(json['ready_for_scheduler_dry_run']) ?? false,
      readyForSchedulerRealOrder:
          _boolValue(json['ready_for_scheduler_real_order']) ?? false,
      blockReasons: _stringList(json['block_reasons']),
      rawPayload: json,
    );
  }

  final bool available;
  final String statusEndpoint;
  final bool readOnly;
  final bool stopLossExecutionEnabled;
  final bool takeProfitExecutionEnabled;
  final bool liveAutoSellEnabled;
  final bool autoBuyExecutionEnabled;
  final bool liveAutoBuyEnabled;
  final bool dryRun;
  final int? dailyLimitRemaining;
  final bool readyForSchedulerDryRun;
  final bool readyForSchedulerRealOrder;
  final List<String> blockReasons;
  final Map<String, dynamic> rawPayload;
}

class KisSchedulerRecentRun {
  const KisSchedulerRecentRun({
    required this.triggerSource,
    required this.mode,
    required this.result,
    required this.symbol,
    required this.action,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    this.createdAt,
    this.blockReasons = const [],
  });

  factory KisSchedulerRecentRun.fromJson(Map<String, dynamic> json) {
    return KisSchedulerRecentRun(
      createdAt: _nullableString(json['created_at']),
      triggerSource: _stringValue(json['trigger_source'], fallback: 'n/a'),
      mode: _stringValue(json['mode'], fallback: 'n/a'),
      result: _stringValue(json['result'], fallback: 'n/a'),
      symbol: _stringValue(json['symbol'], fallback: 'n/a'),
      action: _stringValue(json['action'], fallback: 'hold'),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      blockReasons: _stringList(json['block_reasons']),
    );
  }

  final String? createdAt;
  final String triggerSource;
  final String mode;
  final String result;
  final String symbol;
  final String action;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final List<String> blockReasons;
}

List<KisSchedulerScheduleItem> _scheduleList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisSchedulerScheduleItem.fromJson(Map<String, dynamic>.from(item)))
      .toList();
}

List<KisSchedulerRecentRun> _recentRunList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) =>
          KisSchedulerRecentRun.fromJson(Map<String, dynamic>.from(item)))
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
