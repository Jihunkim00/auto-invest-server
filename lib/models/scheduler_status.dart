class SchedulerStatus {
  const SchedulerStatus({
    required this.runtimeSchedulerEnabled,
    required this.us,
    required this.kr,
    this.global = const SchedulerGlobalStatus.safe(),
    this.currentOperationMode = 'safe_mode',
    this.displayModeLabel = '',
    this.displayWarningLevel = '',
    this.userFriendlySummary = '',
    this.riskSummary = const SchedulerRiskSummary.safe(),
    this.liveOrderPossible = false,
    this.liveBuyPossible = false,
    this.liveSellPossible = false,
    this.dailyLiveOrderRemaining,
    this.warningMessage = '',
  });

  factory SchedulerStatus.fromJson(Map<String, dynamic> json) {
    final globalJson =
        Map<String, dynamic>.from((json['global'] as Map?) ?? {});
    final us = MarketSchedulerStatus.fromJson(
      _mergedBrokerJson(json, modernKey: 'alpaca', legacyKey: 'US'),
    );
    final kr = MarketSchedulerStatus.fromJson(
      _mergedBrokerJson(json, modernKey: 'kis', legacyKey: 'KR'),
      isKr: true,
    );
    final riskSummary = SchedulerRiskSummary.fromJson(
      Map<String, dynamic>.from((json['risk_summary'] as Map?) ?? {}),
    );
    final effectiveRiskSummary =
        riskSummary.warningLevel == 'safe' && json['risk_summary'] == null
            ? kr.riskSummary
            : riskSummary;
    final runtimeSchedulerEnabled =
        _readBool(json['runtime_scheduler_enabled']) ??
            _readBool(globalJson['scheduler_enabled']) ??
            false;
    final currentOperationMode =
        _readString(json['current_operation_mode'], 'safe_mode');
    return SchedulerStatus(
      runtimeSchedulerEnabled: runtimeSchedulerEnabled,
      global: SchedulerGlobalStatus.fromJson(
        globalJson,
        fallbackSchedulerEnabled: runtimeSchedulerEnabled,
        fallbackDryRun: effectiveRiskSummary.dryRun,
        fallbackKillSwitch: effectiveRiskSummary.killSwitch,
        fallbackSafeModeActive: effectiveRiskSummary.safeModeActive ||
            currentOperationMode == 'safe_mode',
      ),
      us: us,
      kr: kr,
      currentOperationMode: currentOperationMode,
      displayModeLabel: _readString(json['display_mode_label'], ''),
      displayWarningLevel: _readString(json['display_warning_level'], ''),
      userFriendlySummary: _readString(json['user_friendly_summary'], ''),
      riskSummary: effectiveRiskSummary,
      liveOrderPossible: _readBool(json['live_order_possible']) ?? false,
      liveBuyPossible: _readBool(json['live_buy_possible']) ?? false,
      liveSellPossible: _readBool(json['live_sell_possible']) ?? false,
      dailyLiveOrderRemaining:
          _readNullableInt(json['daily_live_order_remaining']) ??
              effectiveRiskSummary.dailyLiveOrderRemaining,
      warningMessage: _readString(json['warning_message'], ''),
    );
  }

  factory SchedulerStatus.safeDefault() {
    return const SchedulerStatus(
      runtimeSchedulerEnabled: false,
      global: SchedulerGlobalStatus.safe(),
      us: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: [],
        market: 'US',
        broker: 'alpaca',
        noNewEntryAfter: '15:45',
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: false,
        timezone: 'Asia/Seoul',
        slots: [],
        market: 'KR',
        broker: 'kis',
        previewOnly: true,
        realOrdersAllowed: false,
        noNewEntryAfter: '14:50',
      ),
      currentOperationMode: 'safe_mode',
      displayModeLabel: 'Safe Mode',
      displayWarningLevel: 'safe',
      userFriendlySummary:
          'Safe mode is active. Scheduler live buy and sell automation are disabled.',
      warningMessage: 'No scheduler live buy or sell automation is armed.',
    );
  }

  final bool runtimeSchedulerEnabled;
  final SchedulerGlobalStatus global;
  final MarketSchedulerStatus us;
  final MarketSchedulerStatus kr;
  final String currentOperationMode;
  final String displayModeLabel;
  final String displayWarningLevel;
  final String userFriendlySummary;
  final SchedulerRiskSummary riskSummary;
  final bool liveOrderPossible;
  final bool liveBuyPossible;
  final bool liveSellPossible;
  final int? dailyLiveOrderRemaining;
  final String warningMessage;

  String get modeLabel {
    if (displayModeLabel.trim().isNotEmpty) return displayModeLabel;
    return operationModeLabel(currentOperationMode);
  }

  String get warningLevel {
    if (displayWarningLevel.trim().isNotEmpty) return displayWarningLevel;
    return riskSummary.warningLevel;
  }
}

class SchedulerGlobalStatus {
  const SchedulerGlobalStatus({
    required this.schedulerEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.safeModeActive,
  });

  const SchedulerGlobalStatus.safe()
      : schedulerEnabled = false,
        dryRun = true,
        killSwitch = false,
        safeModeActive = true;

  factory SchedulerGlobalStatus.fromJson(
    Map<String, dynamic> json, {
    required bool fallbackSchedulerEnabled,
    required bool fallbackDryRun,
    required bool fallbackKillSwitch,
    required bool fallbackSafeModeActive,
  }) {
    return SchedulerGlobalStatus(
      schedulerEnabled:
          _readBool(json['scheduler_enabled']) ?? fallbackSchedulerEnabled,
      dryRun: _readBool(json['dry_run']) ?? fallbackDryRun,
      killSwitch: _readBool(json['kill_switch']) ?? fallbackKillSwitch,
      safeModeActive:
          _readBool(json['safe_mode_active']) ?? fallbackSafeModeActive,
    );
  }

  final bool schedulerEnabled;
  final bool dryRun;
  final bool killSwitch;
  final bool safeModeActive;
}

class MarketSchedulerStatus {
  const MarketSchedulerStatus({
    required this.enabledForScheduler,
    required this.timezone,
    required this.slots,
    this.market = '',
    this.broker = '',
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
    this.noNewEntryAfter,
    this.displayNextRun,
    this.displayNoNewEntryAfter,
    this.liveBuyArmed = false,
    this.liveSellArmed = false,
    this.riskSummary = const SchedulerRiskSummary.safe(),
  });

  factory MarketSchedulerStatus.fromJson(
    Map<String, dynamic> json, {
    bool isKr = false,
  }) {
    final riskSummary = SchedulerRiskSummary.fromJson(
      Map<String, dynamic>.from((json['risk_summary'] as Map?) ?? {}),
    );
    final nextSlotTimeLocal =
        _readNullableString(json['next_slot_time_local'] ?? json['next_run']);
    final noNewEntryAfter = _readNullableString(
        json['no_new_entry_after'] ?? json['kr_no_new_entry_after']);
    return MarketSchedulerStatus(
      enabledForScheduler: _readBool(json['scheduler_enabled']) ??
          _readBool(json['enabled_for_scheduler']) ??
          false,
      market: _readString(json['market'], isKr ? 'KR' : 'US'),
      broker: _readString(json['broker'], isKr ? 'kis' : 'alpaca'),
      timezone: _readString(json['timezone'], ''),
      slots: _readSlots(json['slots']),
      previewOnly: _readBool(json['preview_only']) ?? false,
      realOrdersAllowed: _readBool(json['real_orders_allowed']) ?? false,
      realOrderSchedulerEnabled:
          _readBool(json['real_order_scheduler_enabled']) ?? false,
      liveSchedulerReady: _readBool(json['live_scheduler_ready']) ?? false,
      krSchedulerAnyEnabled:
          _readBool(json['kr_scheduler_any_enabled']) ?? false,
      krLiveSchedulerEnabledEffective:
          _readBool(json['kr_live_scheduler_enabled_effective']) ?? false,
      krDryRunSchedulerEnabledEffective:
          _readBool(json['kr_dry_run_scheduler_enabled_effective']) ?? false,
      enabledForSchedulerBlockReasons:
          _readStringList(json['enabled_for_scheduler_block_reasons']),
      nextSlotName: _readNullableString(json['next_slot_name']),
      nextSlotTimeLocal: nextSlotTimeLocal,
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
      noNewEntryAfter: noNewEntryAfter,
      displayNextRun: _readNullableString(json['display_next_run']) ??
          _displayNextRun(
            _readNullableString(json['next_slot_name']),
            nextSlotTimeLocal,
          ),
      displayNoNewEntryAfter:
          _readNullableString(json['display_no_new_entry_after']) ??
              noNewEntryAfter,
      liveBuyArmed:
          _readBool(json['live_buy_armed']) ?? riskSummary.liveBuyArmed,
      liveSellArmed:
          _readBool(json['live_sell_armed']) ?? riskSummary.liveSellArmed,
      riskSummary: riskSummary,
    );
  }

  final bool enabledForScheduler;
  final String market;
  final String broker;
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
  final String? noNewEntryAfter;
  final String? displayNextRun;
  final String? displayNoNewEntryAfter;
  final bool liveBuyArmed;
  final bool liveSellArmed;
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

String operationModeLabel(String mode) {
  switch (mode) {
    case 'safe_mode':
      return 'Safe Mode';
    case 'dry_run_simulation':
      return 'Dry-run Simulation';
    case 'manual_live_trading':
      return 'Manual Live Trading';
    case 'kis_sell_only_automation':
      return 'KIS Sell-only Automation';
    case 'full_live_test_mode':
      return 'Full Live Test Mode';
  }
  return mode.trim().isEmpty ? 'Unknown Mode' : mode;
}

Map<String, dynamic> _mergedBrokerJson(
  Map<String, dynamic> json, {
  required String modernKey,
  required String legacyKey,
}) {
  final legacy = Map<String, dynamic>.from((json[legacyKey] as Map?) ?? {});
  final modern = Map<String, dynamic>.from((json[modernKey] as Map?) ?? {});
  return {...legacy, ...modern};
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

bool? _readBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes' || text == 'on') {
    return true;
  }
  if (text == 'false' || text == '0' || text == 'no' || text == 'off') {
    return false;
  }
  return null;
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

String? _displayNextRun(String? slotName, String? slotTime) {
  if (slotTime == null || slotTime.trim().isEmpty) return null;
  if (slotName == null || slotName.trim().isEmpty) return slotTime;
  return '$slotName $slotTime';
}
