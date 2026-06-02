class SchedulerStatus {
  const SchedulerStatus({
    required this.runtimeSchedulerEnabled,
    required this.us,
    required this.kr,
  });

  factory SchedulerStatus.fromJson(Map<String, dynamic> json) {
    return SchedulerStatus(
      runtimeSchedulerEnabled: json['runtime_scheduler_enabled'] == true,
      us: MarketSchedulerStatus.fromJson(
          Map<String, dynamic>.from((json['US'] as Map?) ?? {})),
      kr: MarketSchedulerStatus.fromJson(
        Map<String, dynamic>.from((json['KR'] as Map?) ?? {}),
        isKr: true,
      ),
    );
  }

  factory SchedulerStatus.safeDefault() {
    return const SchedulerStatus(
      runtimeSchedulerEnabled: false,
      us: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: [],
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: false,
        timezone: 'Asia/Seoul',
        slots: [],
        previewOnly: true,
        realOrdersAllowed: false,
      ),
    );
  }

  final bool runtimeSchedulerEnabled;
  final MarketSchedulerStatus us;
  final MarketSchedulerStatus kr;
}

class MarketSchedulerStatus {
  const MarketSchedulerStatus({
    required this.enabledForScheduler,
    required this.timezone,
    required this.slots,
    this.previewOnly = false,
    this.realOrdersAllowed = false,
    this.realOrderSchedulerEnabled = false,
    this.liveSchedulerReady = false,
    this.krSchedulerAnyEnabled = false,
    this.krLiveSchedulerEnabledEffective = false,
    this.krDryRunSchedulerEnabledEffective = false,
    this.enabledForSchedulerBlockReasons = const [],
    this.nextSlotName,
    this.nextSlotTimeLocal,
    this.lastSchedulerRunAt,
    this.lastSchedulerRunResult,
    this.lastSchedulerRunReason,
    this.lastSchedulerRunId,
    this.lastSchedulerRunMode,
    this.lastSchedulerRunTriggerSource,
    this.riskSummary = const SchedulerRiskSummary.safe(),
  });

  factory MarketSchedulerStatus.fromJson(
    Map<String, dynamic> json, {
    bool isKr = false,
  }) {
    return MarketSchedulerStatus(
      enabledForScheduler: json['enabled_for_scheduler'] == true,
      timezone: _readString(json['timezone'], ''),
      slots: _readSlots(json['slots']),
      previewOnly: json['preview_only'] == true,
      realOrdersAllowed: json['real_orders_allowed'] == true,
      realOrderSchedulerEnabled: json['real_order_scheduler_enabled'] == true,
      liveSchedulerReady: json['live_scheduler_ready'] == true,
      krSchedulerAnyEnabled: json['kr_scheduler_any_enabled'] == true,
      krLiveSchedulerEnabledEffective:
          json['kr_live_scheduler_enabled_effective'] == true,
      krDryRunSchedulerEnabledEffective:
          json['kr_dry_run_scheduler_enabled_effective'] == true,
      enabledForSchedulerBlockReasons:
          _readStringList(json['enabled_for_scheduler_block_reasons']),
      nextSlotName: _readNullableString(json['next_slot_name']),
      nextSlotTimeLocal: _readNullableString(json['next_slot_time_local']),
      lastSchedulerRunAt: _readNullableString(json['last_scheduler_run_at']),
      lastSchedulerRunResult:
          _readNullableString(json['last_scheduler_run_result']),
      lastSchedulerRunReason:
          _readNullableString(json['last_scheduler_run_reason']),
      lastSchedulerRunId: _readNullableString(json['last_scheduler_run_id']),
      lastSchedulerRunMode:
          isKr ? _readNullableString(json['last_scheduler_run_mode']) : null,
      lastSchedulerRunTriggerSource: isKr
          ? _readNullableString(json['last_scheduler_run_trigger_source'])
          : null,
      riskSummary: SchedulerRiskSummary.fromJson(
        Map<String, dynamic>.from((json['risk_summary'] as Map?) ?? {}),
      ),
    );
  }

  final bool enabledForScheduler;
  final String timezone;
  final List<String> slots;
  final bool previewOnly;
  final bool realOrdersAllowed;
  final bool realOrderSchedulerEnabled;
  final bool liveSchedulerReady;
  final bool krSchedulerAnyEnabled;
  final bool krLiveSchedulerEnabledEffective;
  final bool krDryRunSchedulerEnabledEffective;
  final List<String> enabledForSchedulerBlockReasons;
  final String? nextSlotName;
  final String? nextSlotTimeLocal;
  final String? lastSchedulerRunAt;
  final String? lastSchedulerRunResult;
  final String? lastSchedulerRunReason;
  final String? lastSchedulerRunId;
  final String? lastSchedulerRunMode;
  final String? lastSchedulerRunTriggerSource;
  final SchedulerRiskSummary riskSummary;
}

class SchedulerRiskSummary {
  const SchedulerRiskSummary({
    required this.liveSellArmed,
    required this.liveBuyArmed,
    required this.sellOnlyMode,
    required this.dailyLiveOrderLimit,
    required this.dailyLiveOrderRemaining,
    required this.maxNotionalPct,
    required this.dryRun,
    required this.killSwitch,
    required this.safeModeActive,
    required this.riskyFlags,
    required this.blockingFlags,
    required this.warningLevel,
    required this.sellGateEnabled,
    required this.buyGateEnabled,
  });

  const SchedulerRiskSummary.safe()
      : liveSellArmed = false,
        liveBuyArmed = false,
        sellOnlyMode = false,
        dailyLiveOrderLimit = 1,
        dailyLiveOrderRemaining = null,
        maxNotionalPct = 0.03,
        dryRun = true,
        killSwitch = false,
        safeModeActive = true,
        riskyFlags = const [],
        blockingFlags = const [],
        warningLevel = 'safe',
        sellGateEnabled = false,
        buyGateEnabled = false;

  factory SchedulerRiskSummary.fromJson(Map<String, dynamic> json) {
    if (json.isEmpty) return const SchedulerRiskSummary.safe();
    return SchedulerRiskSummary(
      liveSellArmed: json['live_sell_armed'] == true,
      liveBuyArmed: json['live_buy_armed'] == true,
      sellOnlyMode: json['sell_only_mode'] == true,
      dailyLiveOrderLimit: _readInt(json['daily_live_order_limit'], 1),
      dailyLiveOrderRemaining:
          _readNullableInt(json['daily_live_order_remaining']),
      maxNotionalPct: _readDouble(json['max_notional_pct'], 0.03),
      dryRun: json['dry_run'] != false,
      killSwitch: json['kill_switch'] == true,
      safeModeActive: json['safe_mode_active'] == true,
      riskyFlags: _readStringList(json['risky_flags']),
      blockingFlags: _readStringList(json['blocking_flags']),
      warningLevel: _readString(json['warning_level'], 'safe'),
      sellGateEnabled: json['sell_gate_enabled'] == true,
      buyGateEnabled: json['buy_gate_enabled'] == true,
    );
  }

  final bool liveSellArmed;
  final bool liveBuyArmed;
  final bool sellOnlyMode;
  final int dailyLiveOrderLimit;
  final int? dailyLiveOrderRemaining;
  final double maxNotionalPct;
  final bool dryRun;
  final bool killSwitch;
  final bool safeModeActive;
  final List<String> riskyFlags;
  final List<String> blockingFlags;
  final String warningLevel;
  final bool sellGateEnabled;
  final bool buyGateEnabled;
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

List<String> _readSlots(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) {
        if (item is Map) {
          final name = item['name']?.toString() ?? '';
          final time = item['time']?.toString() ?? '';
          if (name.isEmpty) return time;
          if (time.isEmpty) return name;
          return '$name $time';
        }
        return item.toString();
      })
      .where((item) => item.trim().isNotEmpty)
      .toList();
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString().trim())
      .where((item) => item.isNotEmpty && item != 'null')
      .toList();
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

double _readDouble(Object? value, double fallback) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? fallback;
}
