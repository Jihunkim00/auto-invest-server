class OpsSettings {
  const OpsSettings({
    required this.schedulerEnabled,
    required this.botEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.brokerMode,
    required this.defaultGateLevel,
    required this.maxDailyTrades,
    required this.maxDailyEntries,
    required this.minEntryScore,
    required this.minScoreGap,
    this.kisLiveAutoEnabled = false,
    this.kisLiveAutoBuyEnabled = false,
    this.kisLiveAutoSellEnabled = false,
    this.kisLiveAutoRequiresManualConfirm = true,
    this.kisLiveAutoMaxOrdersPerDay = 1,
    this.kisLiveAutoMaxNotionalPct = 0.03,
  });

  final bool schedulerEnabled;
  final bool botEnabled;
  final bool dryRun;
  final bool killSwitch;
  final String brokerMode;
  final int defaultGateLevel;
  final int maxDailyTrades;
  final int maxDailyEntries;
  final int minEntryScore;
  final int minScoreGap;
  final bool kisLiveAutoEnabled;
  final bool kisLiveAutoBuyEnabled;
  final bool kisLiveAutoSellEnabled;
  final bool kisLiveAutoRequiresManualConfirm;
  final int kisLiveAutoMaxOrdersPerDay;
  final double kisLiveAutoMaxNotionalPct;

  OpsSettings copyWith({
    bool? schedulerEnabled,
    bool? botEnabled,
    bool? dryRun,
    bool? killSwitch,
    String? brokerMode,
    int? defaultGateLevel,
    int? maxDailyTrades,
    int? maxDailyEntries,
    int? minEntryScore,
    int? minScoreGap,
    bool? kisLiveAutoEnabled,
    bool? kisLiveAutoBuyEnabled,
    bool? kisLiveAutoSellEnabled,
    bool? kisLiveAutoRequiresManualConfirm,
    int? kisLiveAutoMaxOrdersPerDay,
    double? kisLiveAutoMaxNotionalPct,
  }) {
    return OpsSettings(
      schedulerEnabled: schedulerEnabled ?? this.schedulerEnabled,
      botEnabled: botEnabled ?? this.botEnabled,
      dryRun: dryRun ?? this.dryRun,
      killSwitch: killSwitch ?? this.killSwitch,
      brokerMode: brokerMode ?? this.brokerMode,
      defaultGateLevel: defaultGateLevel ?? this.defaultGateLevel,
      maxDailyTrades: maxDailyTrades ?? this.maxDailyTrades,
      maxDailyEntries: maxDailyEntries ?? this.maxDailyEntries,
      minEntryScore: minEntryScore ?? this.minEntryScore,
      minScoreGap: minScoreGap ?? this.minScoreGap,
      kisLiveAutoEnabled: kisLiveAutoEnabled ?? this.kisLiveAutoEnabled,
      kisLiveAutoBuyEnabled:
          kisLiveAutoBuyEnabled ?? this.kisLiveAutoBuyEnabled,
      kisLiveAutoSellEnabled:
          kisLiveAutoSellEnabled ?? this.kisLiveAutoSellEnabled,
      kisLiveAutoRequiresManualConfirm: kisLiveAutoRequiresManualConfirm ??
          this.kisLiveAutoRequiresManualConfirm,
      kisLiveAutoMaxOrdersPerDay:
          kisLiveAutoMaxOrdersPerDay ?? this.kisLiveAutoMaxOrdersPerDay,
      kisLiveAutoMaxNotionalPct:
          kisLiveAutoMaxNotionalPct ?? this.kisLiveAutoMaxNotionalPct,
    );
  }
}
