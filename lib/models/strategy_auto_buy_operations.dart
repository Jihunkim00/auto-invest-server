class StrategyAutoBuyOperationsStatus {
  const StrategyAutoBuyOperationsStatus({
    required this.provider,
    required this.market,
    required this.autoBuyStage,
    required this.nextOperatorAction,
    required this.dryRun,
    required this.scheduler,
    required this.promotions,
    required this.liveReadiness,
    required this.liveAttempts,
    required this.risk,
    required this.safety,
    this.activeProfile,
  });

  final String provider;
  final String market;
  final String? activeProfile;
  final String autoBuyStage;
  final String nextOperatorAction;
  final StrategyAutoBuyOperationsDryRun dryRun;
  final StrategyAutoBuyOperationsScheduler scheduler;
  final StrategyAutoBuyOperationsPromotions promotions;
  final StrategyAutoBuyOperationsLiveReadiness liveReadiness;
  final StrategyAutoBuyOperationsLiveAttempts liveAttempts;
  final StrategyAutoBuyOperationsRisk risk;
  final Map<String, dynamic> safety;

  bool get readyForOperatorConfirm =>
      autoBuyStage == 'ready_for_operator_confirm' && liveReadiness.ready;

  factory StrategyAutoBuyOperationsStatus.fromJson(Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsStatus(
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      activeProfile: _nullableString(json['active_profile']),
      autoBuyStage: _string(json['auto_buy_stage'], 'no_dry_run'),
      nextOperatorAction: _string(json['next_operator_action'], 'run_dry_run'),
      dryRun: StrategyAutoBuyOperationsDryRun.fromJson(
        _map(json['dry_run']),
      ),
      scheduler: StrategyAutoBuyOperationsScheduler.fromJson(
        _map(json['scheduler']),
      ),
      promotions: StrategyAutoBuyOperationsPromotions.fromJson(
        _map(json['promotions']),
      ),
      liveReadiness: StrategyAutoBuyOperationsLiveReadiness.fromJson(
        _map(json['live_readiness']),
      ),
      liveAttempts: StrategyAutoBuyOperationsLiveAttempts.fromJson(
        _map(json['live_attempts']),
      ),
      risk: StrategyAutoBuyOperationsRisk.fromJson(_map(json['risk'])),
      safety: _map(json['safety']),
    );
  }
}

class StrategyAutoBuyOperationsScheduler {
  const StrategyAutoBuyOperationsScheduler({
    required this.enabled,
    required this.dryRunOnly,
    required this.allowLiveOrders,
    required this.runsToday,
    required this.maxRunsPerDay,
    required this.minMinutesBetweenRuns,
    this.latestRunStatus,
    this.nextAllowedRunAt,
  });

  final bool enabled;
  final bool dryRunOnly;
  final bool allowLiveOrders;
  final int runsToday;
  final int maxRunsPerDay;
  final String? latestRunStatus;
  final DateTime? nextAllowedRunAt;
  final int minMinutesBetweenRuns;

  factory StrategyAutoBuyOperationsScheduler.fromJson(
      Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsScheduler(
      enabled: json['enabled'] == true,
      dryRunOnly: json['dry_run_only'] != false,
      allowLiveOrders: json['allow_live_orders'] == true,
      runsToday: _int(json['runs_today']),
      maxRunsPerDay: _int(json['max_runs_per_day']),
      latestRunStatus: _nullableString(json['latest_run_status']),
      nextAllowedRunAt: _dateTime(json['next_allowed_run_at']),
      minMinutesBetweenRuns: _int(json['min_minutes_between_runs']),
    );
  }
}

class StrategyAutoBuyOperationsPromotions {
  const StrategyAutoBuyOperationsPromotions({
    required this.pendingCount,
    required this.acknowledgedCountToday,
    required this.dismissedCountToday,
    this.latestSymbol,
    this.latestStatus,
    this.latestExpiresAt,
  });

  final int pendingCount;
  final String? latestSymbol;
  final String? latestStatus;
  final DateTime? latestExpiresAt;
  final int acknowledgedCountToday;
  final int dismissedCountToday;

  factory StrategyAutoBuyOperationsPromotions.fromJson(
      Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsPromotions(
      pendingCount: _int(json['pending_count']),
      latestSymbol: _nullableString(json['latest_symbol']),
      latestStatus: _nullableString(json['latest_status']),
      latestExpiresAt: _dateTime(json['latest_expires_at']),
      acknowledgedCountToday: _int(json['acknowledged_count_today']),
      dismissedCountToday: _int(json['dismissed_count_today']),
    );
  }
}

class StrategyAutoBuyOperationsDryRun {
  const StrategyAutoBuyOperationsDryRun({
    required this.recentFound,
    required this.wouldBuyCountToday,
    required this.blockedCountToday,
    required this.summary,
    this.latestAction,
    this.latestSymbol,
    this.latestScore,
    this.latestTime,
  });

  final bool recentFound;
  final String? latestAction;
  final String? latestSymbol;
  final double? latestScore;
  final DateTime? latestTime;
  final int wouldBuyCountToday;
  final int blockedCountToday;
  final Map<String, dynamic> summary;

  factory StrategyAutoBuyOperationsDryRun.fromJson(Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsDryRun(
      recentFound: json['recent_found'] == true,
      latestAction: _nullableString(json['latest_action']),
      latestSymbol: _nullableString(json['latest_symbol']),
      latestScore: _nullableDouble(json['latest_score']),
      latestTime: _dateTime(json['latest_time']),
      wouldBuyCountToday: _int(json['would_buy_count_today']),
      blockedCountToday: _int(json['blocked_count_today']),
      summary: _map(json['summary']),
    );
  }
}

class StrategyAutoBuyOperationsLiveReadiness {
  const StrategyAutoBuyOperationsLiveReadiness({
    required this.ready,
    required this.enabled,
    required this.recentDryRunRequired,
    required this.recentDryRunFound,
    required this.killSwitch,
    required this.kisRealOrderEnabled,
    required this.targetRiskReady,
    required this.ordersRemainingToday,
    this.primaryBlockReason,
    this.dryRunStatus,
  });

  final bool ready;
  final bool enabled;
  final String? primaryBlockReason;
  final bool recentDryRunRequired;
  final bool recentDryRunFound;
  final String? dryRunStatus;
  final bool killSwitch;
  final bool kisRealOrderEnabled;
  final bool targetRiskReady;
  final int ordersRemainingToday;

  factory StrategyAutoBuyOperationsLiveReadiness.fromJson(
      Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsLiveReadiness(
      ready: json['ready'] == true,
      enabled: json['enabled'] == true,
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      recentDryRunRequired: json['recent_dry_run_required'] == true,
      recentDryRunFound: json['recent_dry_run_found'] == true,
      dryRunStatus: _nullableString(json['dry_run_status']),
      killSwitch: json['kill_switch'] == true,
      kisRealOrderEnabled: json['kis_real_order_enabled'] == true,
      targetRiskReady: json['target_risk_ready'] == true,
      ordersRemainingToday: _int(json['orders_remaining_today']),
    );
  }
}

class StrategyAutoBuyOperationsLiveAttempts {
  const StrategyAutoBuyOperationsLiveAttempts({
    required this.submittedCountToday,
    required this.blockedCountToday,
    required this.syncRequiredCount,
    required this.recent,
    this.latestStatus,
  });

  final String? latestStatus;
  final int submittedCountToday;
  final int blockedCountToday;
  final int syncRequiredCount;
  final List<Map<String, dynamic>> recent;

  factory StrategyAutoBuyOperationsLiveAttempts.fromJson(
      Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsLiveAttempts(
      latestStatus: _nullableString(json['latest_status']),
      submittedCountToday: _int(json['submitted_count_today']),
      blockedCountToday: _int(json['blocked_count_today']),
      syncRequiredCount: _int(json['sync_required_count']),
      recent: _maps(json['recent']),
    );
  }
}

class StrategyAutoBuyOperationsRisk {
  const StrategyAutoBuyOperationsRisk({
    required this.entryAllowed,
    required this.dailyLossLimitHit,
    required this.monthlyLossLimitHit,
    this.sizeMultiplier,
    this.targetProgressPct,
  });

  final bool entryAllowed;
  final double? sizeMultiplier;
  final double? targetProgressPct;
  final bool dailyLossLimitHit;
  final bool monthlyLossLimitHit;

  factory StrategyAutoBuyOperationsRisk.fromJson(Map<String, dynamic> json) {
    return StrategyAutoBuyOperationsRisk(
      entryAllowed: json['entry_allowed'] == true,
      sizeMultiplier: _nullableDouble(json['size_multiplier']),
      targetProgressPct: _nullableDouble(json['target_progress_pct']),
      dailyLossLimitHit: json['daily_loss_limit_hit'] == true,
      monthlyLossLimitHit: json['monthly_loss_limit_hit'] == true,
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

int _int(Object? value) => _nullableInt(value) ?? 0;

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

double? _nullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString().replaceAll(',', '').trim());
}

DateTime? _dateTime(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}

Map<String, dynamic> _map(Object? value) {
  return value is Map ? Map<String, dynamic>.from(value) : const {};
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
}
