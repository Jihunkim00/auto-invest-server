class OpsSettings {
  const OpsSettings({
    required this.schedulerEnabled,
    required this.botEnabled,
    required this.dryRun,
    required this.killSwitch,
    required this.brokerMode,
    required this.maxDailyTrades,
    required this.maxDailyEntries,
    required this.minEntryScore,
    required this.minScoreGap,
    this.updatedAt,
  });

  final bool schedulerEnabled;
  final bool botEnabled;
  final bool dryRun;
  final bool killSwitch;
  final String brokerMode;
  final int maxDailyTrades;
  final int maxDailyEntries;
  final int minEntryScore;
  final int minScoreGap;
  final DateTime? updatedAt;

  OpsSettings copyWith({
    bool? schedulerEnabled,
    bool? botEnabled,
    bool? dryRun,
    bool? killSwitch,
    String? brokerMode,
    int? maxDailyTrades,
    int? maxDailyEntries,
    int? minEntryScore,
    int? minScoreGap,
    DateTime? updatedAt,
  }) {
    return OpsSettings(
      schedulerEnabled: schedulerEnabled ?? this.schedulerEnabled,
      botEnabled: botEnabled ?? this.botEnabled,
      dryRun: dryRun ?? this.dryRun,
      killSwitch: killSwitch ?? this.killSwitch,
      brokerMode: brokerMode ?? this.brokerMode,
      maxDailyTrades: maxDailyTrades ?? this.maxDailyTrades,
      maxDailyEntries: maxDailyEntries ?? this.maxDailyEntries,
      minEntryScore: minEntryScore ?? this.minEntryScore,
      minScoreGap: minScoreGap ?? this.minScoreGap,
      updatedAt: updatedAt ?? this.updatedAt,
    );
  }
}
