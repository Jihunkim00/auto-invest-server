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
}
