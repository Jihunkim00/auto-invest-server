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
    this.currentOperationMode = 'safe_mode',
    this.maxLiveOrdersPerDay = 1,
    this.maxPositions = 3,
    this.maxPositionPct = 0.03,
    this.maxOrderNotionalPct = 0.03,
    this.dailyMaxLossPct = 0,
    this.noNewEntryAfter = '14:50',
    this.krNoNewEntryAfter = '14:50',
    this.usNoNewEntryAfter = '15:45',
    this.usNoNewEntryAfterReadOnly = true,
    this.usNoNewEntryAfterDerived = true,
    this.stopLossPct = 0.015,
    this.takeProfitPct = 0.03,
    this.kisLiveAutoEnabled = false,
    this.kisLiveAutoBuyEnabled = false,
    this.kisLiveAutoSellEnabled = false,
    this.kisLiveAutoRequiresManualConfirm = true,
    this.kisLiveAutoMaxOrdersPerDay = 1,
    this.kisLiveAutoMaxNotionalPct = 0.03,
    this.kisLimitedAutoSellEnabled = false,
    this.kisLimitedAutoStopLossEnabled = false,
    this.kisLimitedAutoTakeProfitEnabled = false,
    this.kisLimitedAutoSellStopLossEnabled = false,
    this.kisLimitedAutoSellTakeProfitEnabled = false,
    this.kisLimitedAutoSellRequiresQueueReview = true,
    this.kisLimitedAutoSellMaxOrdersPerDay = 1,
    this.kisLimitedAutoSellMaxNotionalPct = 0.03,
    this.kisLimitedAutoSellMinShadowOccurrences = 1,
    this.kisLimitedAutoSellAllowManualReviewTrigger = false,
    this.kisLimitedAutoSellAllowTakeProfitTrigger = false,
    this.kisLimitedAutoBuyEnabled = false,
    this.kisLimitedAutoBuyReadinessEnabled = true,
    this.kisLimitedAutoBuyShadowEnabled = true,
    this.kisLimitedAutoBuyRequiresShadowReview = true,
    this.kisLimitedAutoBuyMaxOrdersPerDay = 1,
    this.kisLimitedAutoBuyMaxNotionalPct = 0.03,
    this.kisLimitedAutoBuyMinCashBufferKrw = 0,
    this.kisLimitedAutoBuyRequiresExistingSellGuards = true,
    this.kisLimitedAutoBuyMinFinalScore = 75,
    this.kisLimitedAutoBuyMinConfidence = 0.70,
    this.kisLimitedAutoBuyMaxPositions = 3,
    this.kisLimitedAutoBuyBlockIfPositionExists = true,
    this.kisLimitedAutoBuyBlockIfOpenOrderExists = true,
    this.kisLimitedAutoBuyAllowReentrySameDay = false,
    this.kisLimitedAutoBuyRequireMarketOpen = true,
    this.kisLimitedAutoBuyNoNewEntryAfter = '14:50',
    this.kisLimitedAutoBuyAllowGptHardBlock = false,
    this.kisSchedulerEnabled = false,
    this.kisSchedulerDryRun = true,
    this.kisSchedulerLiveEnabled = false,
    this.kisSchedulerAllowRealOrders = false,
    this.kisSchedulerConfiguredAllowRealOrders = false,
    this.kisSchedulerBuyEnabled = false,
    this.kisSchedulerSellEnabled = false,
    this.kisSchedulerAllowLimitedAutoBuy = false,
    this.kisSchedulerAllowLimitedAutoSell = false,
    this.kisSchedulerMaxLiveOrdersPerDay = 1,
    this.kisSchedulerLiveRequiresDryRunFalse = true,
    this.kisSchedulerLiveRespectKillSwitch = true,
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
  final String currentOperationMode;
  final int maxLiveOrdersPerDay;
  final int maxPositions;
  final double maxPositionPct;
  final double maxOrderNotionalPct;
  final double dailyMaxLossPct;
  final String noNewEntryAfter;
  final String krNoNewEntryAfter;
  final String usNoNewEntryAfter;
  final bool usNoNewEntryAfterReadOnly;
  final bool usNoNewEntryAfterDerived;
  final double stopLossPct;
  final double takeProfitPct;
  final bool kisLiveAutoEnabled;
  final bool kisLiveAutoBuyEnabled;
  final bool kisLiveAutoSellEnabled;
  final bool kisLiveAutoRequiresManualConfirm;
  final int kisLiveAutoMaxOrdersPerDay;
  final double kisLiveAutoMaxNotionalPct;
  final bool kisLimitedAutoSellEnabled;
  final bool kisLimitedAutoStopLossEnabled;
  final bool kisLimitedAutoTakeProfitEnabled;
  final bool kisLimitedAutoSellStopLossEnabled;
  final bool kisLimitedAutoSellTakeProfitEnabled;
  final bool kisLimitedAutoSellRequiresQueueReview;
  final int kisLimitedAutoSellMaxOrdersPerDay;
  final double kisLimitedAutoSellMaxNotionalPct;
  final int kisLimitedAutoSellMinShadowOccurrences;
  final bool kisLimitedAutoSellAllowManualReviewTrigger;
  final bool kisLimitedAutoSellAllowTakeProfitTrigger;
  final bool kisLimitedAutoBuyEnabled;
  final bool kisLimitedAutoBuyReadinessEnabled;
  final bool kisLimitedAutoBuyShadowEnabled;
  final bool kisLimitedAutoBuyRequiresShadowReview;
  final int kisLimitedAutoBuyMaxOrdersPerDay;
  final double kisLimitedAutoBuyMaxNotionalPct;
  final double kisLimitedAutoBuyMinCashBufferKrw;
  final bool kisLimitedAutoBuyRequiresExistingSellGuards;
  final double kisLimitedAutoBuyMinFinalScore;
  final double kisLimitedAutoBuyMinConfidence;
  final int kisLimitedAutoBuyMaxPositions;
  final bool kisLimitedAutoBuyBlockIfPositionExists;
  final bool kisLimitedAutoBuyBlockIfOpenOrderExists;
  final bool kisLimitedAutoBuyAllowReentrySameDay;
  final bool kisLimitedAutoBuyRequireMarketOpen;
  final String kisLimitedAutoBuyNoNewEntryAfter;
  final bool kisLimitedAutoBuyAllowGptHardBlock;
  final bool kisSchedulerEnabled;
  final bool kisSchedulerDryRun;
  final bool kisSchedulerLiveEnabled;
  final bool kisSchedulerAllowRealOrders;
  final bool kisSchedulerConfiguredAllowRealOrders;
  final bool kisSchedulerBuyEnabled;
  final bool kisSchedulerSellEnabled;
  final bool kisSchedulerAllowLimitedAutoBuy;
  final bool kisSchedulerAllowLimitedAutoSell;
  final int kisSchedulerMaxLiveOrdersPerDay;
  final bool kisSchedulerLiveRequiresDryRunFalse;
  final bool kisSchedulerLiveRespectKillSwitch;

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
    String? currentOperationMode,
    int? maxLiveOrdersPerDay,
    int? maxPositions,
    double? maxPositionPct,
    double? maxOrderNotionalPct,
    double? dailyMaxLossPct,
    String? noNewEntryAfter,
    String? krNoNewEntryAfter,
    String? usNoNewEntryAfter,
    bool? usNoNewEntryAfterReadOnly,
    bool? usNoNewEntryAfterDerived,
    double? stopLossPct,
    double? takeProfitPct,
    bool? kisLiveAutoEnabled,
    bool? kisLiveAutoBuyEnabled,
    bool? kisLiveAutoSellEnabled,
    bool? kisLiveAutoRequiresManualConfirm,
    int? kisLiveAutoMaxOrdersPerDay,
    double? kisLiveAutoMaxNotionalPct,
    bool? kisLimitedAutoSellEnabled,
    bool? kisLimitedAutoStopLossEnabled,
    bool? kisLimitedAutoTakeProfitEnabled,
    bool? kisLimitedAutoSellStopLossEnabled,
    bool? kisLimitedAutoSellTakeProfitEnabled,
    bool? kisLimitedAutoSellRequiresQueueReview,
    int? kisLimitedAutoSellMaxOrdersPerDay,
    double? kisLimitedAutoSellMaxNotionalPct,
    int? kisLimitedAutoSellMinShadowOccurrences,
    bool? kisLimitedAutoSellAllowManualReviewTrigger,
    bool? kisLimitedAutoSellAllowTakeProfitTrigger,
    bool? kisLimitedAutoBuyEnabled,
    bool? kisLimitedAutoBuyReadinessEnabled,
    bool? kisLimitedAutoBuyShadowEnabled,
    bool? kisLimitedAutoBuyRequiresShadowReview,
    int? kisLimitedAutoBuyMaxOrdersPerDay,
    double? kisLimitedAutoBuyMaxNotionalPct,
    double? kisLimitedAutoBuyMinCashBufferKrw,
    bool? kisLimitedAutoBuyRequiresExistingSellGuards,
    double? kisLimitedAutoBuyMinFinalScore,
    double? kisLimitedAutoBuyMinConfidence,
    int? kisLimitedAutoBuyMaxPositions,
    bool? kisLimitedAutoBuyBlockIfPositionExists,
    bool? kisLimitedAutoBuyBlockIfOpenOrderExists,
    bool? kisLimitedAutoBuyAllowReentrySameDay,
    bool? kisLimitedAutoBuyRequireMarketOpen,
    String? kisLimitedAutoBuyNoNewEntryAfter,
    bool? kisLimitedAutoBuyAllowGptHardBlock,
    bool? kisSchedulerEnabled,
    bool? kisSchedulerDryRun,
    bool? kisSchedulerLiveEnabled,
    bool? kisSchedulerAllowRealOrders,
    bool? kisSchedulerConfiguredAllowRealOrders,
    bool? kisSchedulerBuyEnabled,
    bool? kisSchedulerSellEnabled,
    bool? kisSchedulerAllowLimitedAutoBuy,
    bool? kisSchedulerAllowLimitedAutoSell,
    int? kisSchedulerMaxLiveOrdersPerDay,
    bool? kisSchedulerLiveRequiresDryRunFalse,
    bool? kisSchedulerLiveRespectKillSwitch,
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
      currentOperationMode: currentOperationMode ?? this.currentOperationMode,
      maxLiveOrdersPerDay: maxLiveOrdersPerDay ?? this.maxLiveOrdersPerDay,
      maxPositions: maxPositions ?? this.maxPositions,
      maxPositionPct: maxPositionPct ?? this.maxPositionPct,
      maxOrderNotionalPct: maxOrderNotionalPct ?? this.maxOrderNotionalPct,
      dailyMaxLossPct: dailyMaxLossPct ?? this.dailyMaxLossPct,
      noNewEntryAfter: noNewEntryAfter ?? this.noNewEntryAfter,
      krNoNewEntryAfter: krNoNewEntryAfter ?? this.krNoNewEntryAfter,
      usNoNewEntryAfter: usNoNewEntryAfter ?? this.usNoNewEntryAfter,
      usNoNewEntryAfterReadOnly:
          usNoNewEntryAfterReadOnly ?? this.usNoNewEntryAfterReadOnly,
      usNoNewEntryAfterDerived:
          usNoNewEntryAfterDerived ?? this.usNoNewEntryAfterDerived,
      stopLossPct: stopLossPct ?? this.stopLossPct,
      takeProfitPct: takeProfitPct ?? this.takeProfitPct,
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
      kisLimitedAutoSellEnabled:
          kisLimitedAutoSellEnabled ?? this.kisLimitedAutoSellEnabled,
      kisLimitedAutoStopLossEnabled:
          kisLimitedAutoStopLossEnabled ?? this.kisLimitedAutoStopLossEnabled,
      kisLimitedAutoTakeProfitEnabled: kisLimitedAutoTakeProfitEnabled ??
          this.kisLimitedAutoTakeProfitEnabled,
      kisLimitedAutoSellStopLossEnabled: kisLimitedAutoSellStopLossEnabled ??
          this.kisLimitedAutoSellStopLossEnabled,
      kisLimitedAutoSellTakeProfitEnabled:
          kisLimitedAutoSellTakeProfitEnabled ??
              this.kisLimitedAutoSellTakeProfitEnabled,
      kisLimitedAutoSellRequiresQueueReview:
          kisLimitedAutoSellRequiresQueueReview ??
              this.kisLimitedAutoSellRequiresQueueReview,
      kisLimitedAutoSellMaxOrdersPerDay: kisLimitedAutoSellMaxOrdersPerDay ??
          this.kisLimitedAutoSellMaxOrdersPerDay,
      kisLimitedAutoSellMaxNotionalPct: kisLimitedAutoSellMaxNotionalPct ??
          this.kisLimitedAutoSellMaxNotionalPct,
      kisLimitedAutoSellMinShadowOccurrences:
          kisLimitedAutoSellMinShadowOccurrences ??
              this.kisLimitedAutoSellMinShadowOccurrences,
      kisLimitedAutoSellAllowManualReviewTrigger:
          kisLimitedAutoSellAllowManualReviewTrigger ??
              this.kisLimitedAutoSellAllowManualReviewTrigger,
      kisLimitedAutoSellAllowTakeProfitTrigger:
          kisLimitedAutoSellAllowTakeProfitTrigger ??
              this.kisLimitedAutoSellAllowTakeProfitTrigger,
      kisLimitedAutoBuyEnabled:
          kisLimitedAutoBuyEnabled ?? this.kisLimitedAutoBuyEnabled,
      kisLimitedAutoBuyReadinessEnabled: kisLimitedAutoBuyReadinessEnabled ??
          this.kisLimitedAutoBuyReadinessEnabled,
      kisLimitedAutoBuyShadowEnabled:
          kisLimitedAutoBuyShadowEnabled ?? this.kisLimitedAutoBuyShadowEnabled,
      kisLimitedAutoBuyRequiresShadowReview:
          kisLimitedAutoBuyRequiresShadowReview ??
              this.kisLimitedAutoBuyRequiresShadowReview,
      kisLimitedAutoBuyMaxOrdersPerDay: kisLimitedAutoBuyMaxOrdersPerDay ??
          this.kisLimitedAutoBuyMaxOrdersPerDay,
      kisLimitedAutoBuyMaxNotionalPct: kisLimitedAutoBuyMaxNotionalPct ??
          this.kisLimitedAutoBuyMaxNotionalPct,
      kisLimitedAutoBuyMinCashBufferKrw: kisLimitedAutoBuyMinCashBufferKrw ??
          this.kisLimitedAutoBuyMinCashBufferKrw,
      kisLimitedAutoBuyRequiresExistingSellGuards:
          kisLimitedAutoBuyRequiresExistingSellGuards ??
              this.kisLimitedAutoBuyRequiresExistingSellGuards,
      kisLimitedAutoBuyMinFinalScore:
          kisLimitedAutoBuyMinFinalScore ?? this.kisLimitedAutoBuyMinFinalScore,
      kisLimitedAutoBuyMinConfidence:
          kisLimitedAutoBuyMinConfidence ?? this.kisLimitedAutoBuyMinConfidence,
      kisLimitedAutoBuyMaxPositions:
          kisLimitedAutoBuyMaxPositions ?? this.kisLimitedAutoBuyMaxPositions,
      kisLimitedAutoBuyBlockIfPositionExists:
          kisLimitedAutoBuyBlockIfPositionExists ??
              this.kisLimitedAutoBuyBlockIfPositionExists,
      kisLimitedAutoBuyBlockIfOpenOrderExists:
          kisLimitedAutoBuyBlockIfOpenOrderExists ??
              this.kisLimitedAutoBuyBlockIfOpenOrderExists,
      kisLimitedAutoBuyAllowReentrySameDay:
          kisLimitedAutoBuyAllowReentrySameDay ??
              this.kisLimitedAutoBuyAllowReentrySameDay,
      kisLimitedAutoBuyRequireMarketOpen: kisLimitedAutoBuyRequireMarketOpen ??
          this.kisLimitedAutoBuyRequireMarketOpen,
      kisLimitedAutoBuyNoNewEntryAfter: kisLimitedAutoBuyNoNewEntryAfter ??
          this.kisLimitedAutoBuyNoNewEntryAfter,
      kisLimitedAutoBuyAllowGptHardBlock: kisLimitedAutoBuyAllowGptHardBlock ??
          this.kisLimitedAutoBuyAllowGptHardBlock,
      kisSchedulerEnabled: kisSchedulerEnabled ?? this.kisSchedulerEnabled,
      kisSchedulerDryRun: kisSchedulerDryRun ?? this.kisSchedulerDryRun,
      kisSchedulerLiveEnabled:
          kisSchedulerLiveEnabled ?? this.kisSchedulerLiveEnabled,
      kisSchedulerAllowRealOrders:
          kisSchedulerAllowRealOrders ?? this.kisSchedulerAllowRealOrders,
      kisSchedulerConfiguredAllowRealOrders:
          kisSchedulerConfiguredAllowRealOrders ??
              this.kisSchedulerConfiguredAllowRealOrders,
      kisSchedulerBuyEnabled:
          kisSchedulerBuyEnabled ?? this.kisSchedulerBuyEnabled,
      kisSchedulerSellEnabled:
          kisSchedulerSellEnabled ?? this.kisSchedulerSellEnabled,
      kisSchedulerAllowLimitedAutoBuy: kisSchedulerAllowLimitedAutoBuy ??
          this.kisSchedulerAllowLimitedAutoBuy,
      kisSchedulerAllowLimitedAutoSell: kisSchedulerAllowLimitedAutoSell ??
          this.kisSchedulerAllowLimitedAutoSell,
      kisSchedulerMaxLiveOrdersPerDay: kisSchedulerMaxLiveOrdersPerDay ??
          this.kisSchedulerMaxLiveOrdersPerDay,
      kisSchedulerLiveRequiresDryRunFalse:
          kisSchedulerLiveRequiresDryRunFalse ??
              this.kisSchedulerLiveRequiresDryRunFalse,
      kisSchedulerLiveRespectKillSwitch: kisSchedulerLiveRespectKillSwitch ??
          this.kisSchedulerLiveRespectKillSwitch,
    );
  }
}
