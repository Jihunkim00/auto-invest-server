class KisSchedulerDryRunReview {
  const KisSchedulerDryRunReview({
    required this.provider,
    required this.market,
    required this.mode,
    required this.reviewOnly,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.orderLogCreated,
    required this.summary,
    required this.recentRuns,
    required this.topBlockReasons,
    required this.moduleSummary,
    required this.safetyViolations,
    required this.latestRecommendedOperatorAction,
    required this.safety,
    required this.diagnostics,
    required this.rawPayload,
  });

  factory KisSchedulerDryRunReview.fromJson(Map<String, dynamic> json) {
    final summary = KisSchedulerDryRunReviewSummary.fromJson(
      _dynamicMap(json['summary']),
    );
    return KisSchedulerDryRunReview(
      provider: _stringValue(json['provider'], fallback: 'kis'),
      market: _stringValue(json['market'], fallback: 'KR'),
      mode: _stringValue(
        json['mode'],
        fallback: 'kis_scheduler_dry_run_review',
      ),
      reviewOnly: _boolValue(json['review_only']) ?? true,
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      orderLogCreated: _boolValue(json['order_log_created']) ?? false,
      summary: summary,
      recentRuns: _runList(json['recent_runs']),
      topBlockReasons: _blockReasonList(json['top_block_reasons']),
      moduleSummary: _moduleSummaryMap(json['module_summary']),
      safetyViolations: _violationList(json['safety_violations']),
      latestRecommendedOperatorAction: _stringValue(
        json['latest_recommended_operator_action'] ??
            summary.latestRecommendedOperatorAction,
        fallback: 'n/a',
      ),
      safety: _dynamicMap(json['safety']),
      diagnostics: _dynamicMap(json['diagnostics']),
      rawPayload: _dynamicMap(json),
    );
  }

  final String provider;
  final String market;
  final String mode;
  final bool reviewOnly;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool orderLogCreated;
  final KisSchedulerDryRunReviewSummary summary;
  final List<KisSchedulerDryRunReviewRun> recentRuns;
  final List<KisSchedulerDryRunBlockReason> topBlockReasons;
  final Map<String, KisSchedulerDryRunModuleSummary> moduleSummary;
  final List<KisSchedulerDryRunSafetyViolation> safetyViolations;
  final String latestRecommendedOperatorAction;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;
  final Map<String, dynamic> rawPayload;

  KisSchedulerDryRunModuleSummary module(String key) {
    return moduleSummary[key] ?? KisSchedulerDryRunModuleSummary.empty(key);
  }
}

class KisSchedulerDryRunReviewSummary {
  const KisSchedulerDryRunReviewSummary({
    required this.totalRuns,
    required this.completedCount,
    required this.blockedCount,
    required this.partialCount,
    required this.sellCandidatesReviewed,
    required this.buyCandidatesReviewed,
    required this.sellReadyCount,
    required this.buyReadyCount,
    required this.buySkippedAfterSellReviewCount,
    required this.submittedOrderCount,
    required this.brokerSubmitCount,
    required this.manualSubmitCount,
    required this.orderLogCreatedCount,
    required this.noSubmitInvariantOk,
    required this.sellBeforeBuyOrderingOk,
    this.latestRunAt,
    this.latestSlotLabel,
    this.latestResult,
    this.latestPrimaryBlockReason,
    this.latestRecommendedOperatorAction,
  });

  factory KisSchedulerDryRunReviewSummary.fromJson(Map<String, dynamic> json) {
    return KisSchedulerDryRunReviewSummary(
      totalRuns: _intValue(json['total_runs']),
      completedCount: _intValue(json['completed_count']),
      blockedCount: _intValue(json['blocked_count']),
      partialCount: _intValue(json['partial_count']),
      sellCandidatesReviewed: _intValue(json['sell_candidates_reviewed']),
      buyCandidatesReviewed: _intValue(json['buy_candidates_reviewed']),
      sellReadyCount: _intValue(json['sell_ready_count']),
      buyReadyCount: _intValue(json['buy_ready_count']),
      buySkippedAfterSellReviewCount:
          _intValue(json['buy_skipped_after_sell_review_count']),
      submittedOrderCount: _intValue(json['submitted_order_count']),
      brokerSubmitCount: _intValue(json['broker_submit_count']),
      manualSubmitCount: _intValue(json['manual_submit_count']),
      orderLogCreatedCount: _intValue(json['order_log_created_count']),
      noSubmitInvariantOk: _boolValue(json['no_submit_invariant_ok']) ?? true,
      sellBeforeBuyOrderingOk:
          _boolValue(json['sell_before_buy_ordering_ok']) ?? true,
      latestRunAt: _nullableString(json['latest_run_at']),
      latestSlotLabel: _nullableString(json['latest_slot_label']),
      latestResult: _nullableString(json['latest_result']),
      latestPrimaryBlockReason:
          _nullableString(json['latest_primary_block_reason']),
      latestRecommendedOperatorAction:
          _nullableString(json['latest_recommended_operator_action']),
    );
  }

  final int totalRuns;
  final int completedCount;
  final int blockedCount;
  final int partialCount;
  final int sellCandidatesReviewed;
  final int buyCandidatesReviewed;
  final int sellReadyCount;
  final int buyReadyCount;
  final int buySkippedAfterSellReviewCount;
  final int submittedOrderCount;
  final int brokerSubmitCount;
  final int manualSubmitCount;
  final int orderLogCreatedCount;
  final bool noSubmitInvariantOk;
  final bool sellBeforeBuyOrderingOk;
  final String? latestRunAt;
  final String? latestSlotLabel;
  final String? latestResult;
  final String? latestPrimaryBlockReason;
  final String? latestRecommendedOperatorAction;
}

class KisSchedulerDryRunReviewRun {
  const KisSchedulerDryRunReviewRun({
    required this.runId,
    required this.createdAt,
    required this.slotLabel,
    required this.triggerSource,
    required this.mode,
    required this.result,
    required this.blockReasons,
    required this.modulesRequested,
    required this.modulesCompleted,
    required this.modulesBlocked,
    required this.sellCandidatesReviewed,
    required this.buyCandidatesReviewed,
    required this.sellReadyCount,
    required this.buyReadyCount,
    required this.submittedOrderCount,
    required this.brokerSubmitCount,
    required this.manualSubmitCount,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.childRuns,
    this.primaryBlockReason,
  });

  factory KisSchedulerDryRunReviewRun.fromJson(Map<String, dynamic> json) {
    return KisSchedulerDryRunReviewRun(
      runId: _stringValue(json['run_id'], fallback: ''),
      createdAt: _nullableString(json['created_at']),
      slotLabel: _stringValue(json['slot_label'], fallback: 'n/a'),
      triggerSource: _stringValue(json['trigger_source'], fallback: 'n/a'),
      mode: _stringValue(json['mode'], fallback: 'n/a'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
      modulesRequested: _stringList(json['modules_requested']),
      modulesCompleted: _stringList(json['modules_completed']),
      modulesBlocked: _stringList(json['modules_blocked']),
      sellCandidatesReviewed: _intValue(json['sell_candidates_reviewed']),
      buyCandidatesReviewed: _intValue(json['buy_candidates_reviewed']),
      sellReadyCount: _intValue(json['sell_ready_count']),
      buyReadyCount: _intValue(json['buy_ready_count']),
      submittedOrderCount: _intValue(json['submitted_order_count']),
      brokerSubmitCount: _intValue(json['broker_submit_count']),
      manualSubmitCount: _intValue(json['manual_submit_count']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      childRuns: _childList(json['child_runs']),
    );
  }

  final String runId;
  final String? createdAt;
  final String slotLabel;
  final String triggerSource;
  final String mode;
  final String result;
  final String? primaryBlockReason;
  final List<String> blockReasons;
  final List<String> modulesRequested;
  final List<String> modulesCompleted;
  final List<String> modulesBlocked;
  final int sellCandidatesReviewed;
  final int buyCandidatesReviewed;
  final int sellReadyCount;
  final int buyReadyCount;
  final int submittedOrderCount;
  final int brokerSubmitCount;
  final int manualSubmitCount;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final List<KisSchedulerDryRunReviewChild> childRuns;
}

class KisSchedulerDryRunReviewChild {
  const KisSchedulerDryRunReviewChild({
    required this.module,
    required this.result,
    required this.action,
    required this.status,
    required this.blockReasons,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.mode,
    required this.source,
    required this.triggerSource,
    required this.summary,
    this.symbol,
    this.primaryBlockReason,
    this.orderId,
  });

  factory KisSchedulerDryRunReviewChild.fromJson(Map<String, dynamic> json) {
    return KisSchedulerDryRunReviewChild(
      module: _stringValue(json['module'], fallback: 'module'),
      result: _stringValue(json['result'], fallback: 'blocked'),
      action: _stringValue(json['action'], fallback: 'hold'),
      symbol: _nullableString(json['symbol']),
      status: _stringValue(json['status'], fallback: 'n/a'),
      primaryBlockReason: _nullableString(json['primary_block_reason']),
      blockReasons: _stringList(json['block_reasons']),
      realOrderSubmitted: _boolValue(json['real_order_submitted']) ?? false,
      brokerSubmitCalled: _boolValue(json['broker_submit_called']) ?? false,
      manualSubmitCalled: _boolValue(json['manual_submit_called']) ?? false,
      orderId: _nullableString(json['order_id']),
      mode: _stringValue(json['mode'], fallback: ''),
      source: _stringValue(json['source'], fallback: ''),
      triggerSource: _stringValue(json['trigger_source'], fallback: ''),
      summary: _dynamicMap(json['summary']),
    );
  }

  final String module;
  final String result;
  final String action;
  final String? symbol;
  final String status;
  final String? primaryBlockReason;
  final List<String> blockReasons;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final String? orderId;
  final String mode;
  final String source;
  final String triggerSource;
  final Map<String, dynamic> summary;
}

class KisSchedulerDryRunBlockReason {
  const KisSchedulerDryRunBlockReason({
    required this.reason,
    required this.label,
    required this.count,
  });

  factory KisSchedulerDryRunBlockReason.fromJson(Map<String, dynamic> json) {
    final reason = _stringValue(json['reason'], fallback: 'unknown');
    return KisSchedulerDryRunBlockReason(
      reason: reason,
      label: _stringValue(json['label'], fallback: reason),
      count: _intValue(json['count']),
    );
  }

  final String reason;
  final String label;
  final int count;
}

class KisSchedulerDryRunSafetyViolation {
  const KisSchedulerDryRunSafetyViolation({
    required this.reason,
    required this.label,
    this.runId,
    this.module,
    this.count,
  });

  factory KisSchedulerDryRunSafetyViolation.fromJson(
    Map<String, dynamic> json,
  ) {
    final reason = _stringValue(json['reason'], fallback: 'unknown');
    return KisSchedulerDryRunSafetyViolation(
      reason: reason,
      label: _stringValue(json['label'], fallback: reason),
      runId: _nullableString(json['run_id']),
      module: _nullableString(json['module']),
      count: _nullableInt(json['count']),
    );
  }

  final String reason;
  final String label;
  final String? runId;
  final String? module;
  final int? count;
}

class KisSchedulerDryRunModuleSummary {
  const KisSchedulerDryRunModuleSummary({
    required this.module,
    required this.runCount,
    required this.blockedCount,
    required this.sellReadyCount,
    required this.buyReadyCount,
    required this.skippedAfterSellReviewCount,
    required this.reviewedCount,
    this.topBlockReason,
  });

  factory KisSchedulerDryRunModuleSummary.fromJson(
    String module,
    Map<String, dynamic> json,
  ) {
    return KisSchedulerDryRunModuleSummary(
      module: module,
      runCount: _intValue(json['run_count']),
      blockedCount: _intValue(json['blocked_count']),
      sellReadyCount: _intValue(json['sell_ready_count']),
      buyReadyCount: _intValue(json['buy_ready_count']),
      skippedAfterSellReviewCount:
          _intValue(json['skipped_after_sell_review_count']),
      reviewedCount: _intValue(json['reviewed_count']),
      topBlockReason: _nullableString(json['top_block_reason']),
    );
  }

  factory KisSchedulerDryRunModuleSummary.empty(String module) {
    return KisSchedulerDryRunModuleSummary.fromJson(module, const {});
  }

  final String module;
  final int runCount;
  final int blockedCount;
  final int sellReadyCount;
  final int buyReadyCount;
  final int skippedAfterSellReviewCount;
  final int reviewedCount;
  final String? topBlockReason;
}

List<KisSchedulerDryRunReviewRun> _runList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerDryRunReviewRun.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerDryRunReviewChild> _childList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerDryRunReviewChild.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerDryRunBlockReason> _blockReasonList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerDryRunBlockReason.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

List<KisSchedulerDryRunSafetyViolation> _violationList(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => KisSchedulerDryRunSafetyViolation.fromJson(
            Map<String, dynamic>.from(item),
          ))
      .toList();
}

Map<String, KisSchedulerDryRunModuleSummary> _moduleSummaryMap(Object? value) {
  if (value is! Map) return const {};
  final result = <String, KisSchedulerDryRunModuleSummary>{};
  for (final entry in value.entries) {
    if (entry.value is Map) {
      final key = entry.key.toString();
      result[key] = KisSchedulerDryRunModuleSummary.fromJson(
        key,
        Map<String, dynamic>.from(entry.value as Map),
      );
    }
  }
  return result;
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

int _intValue(Object? value) {
  if (value is num) return value.toInt();
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return 0;
  return int.tryParse(text) ?? 0;
}

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map((item) => item.toString())
      .where((item) => item.trim().isNotEmpty)
      .toList();
}
