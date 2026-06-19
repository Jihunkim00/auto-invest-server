class AgentOperationsSnapshot {
  const AgentOperationsSnapshot({
    required this.summary,
    required this.safety,
  });

  final AgentOperationsSummary summary;
  final AgentOperationsSafety safety;

  factory AgentOperationsSnapshot.fromJson(Map<String, dynamic> json) {
    return AgentOperationsSnapshot(
      summary: AgentOperationsSummary.fromJson(_readMap(json['summary'])),
      safety: AgentOperationsSafety.fromJson(_readMap(json['safety'])),
    );
  }

  static AgentOperationsSnapshot empty() {
    return const AgentOperationsSnapshot(
      summary: AgentOperationsSummary(),
      safety: AgentOperationsSafety(),
    );
  }
}

class AgentOperationsSummary {
  const AgentOperationsSummary({
    this.totalPlans = 0,
    this.totalActivePlans = 0,
    this.activePlans = 0,
    this.readyForReviewCount = 0,
    this.pendingAuthCount = 0,
    this.authRequiredCount = 0,
    this.blockedCount = 0,
    this.blockedRunCount = 0,
    this.prefillReadyCount = 0,
    this.safeRunCompletedCount = 0,
    this.failedCount = 0,
    this.activeConversationCount = 0,
    this.archivedConversationCount = 0,
    this.todayMessagesCount = 0,
    this.latestConversationKey,
    this.latestPlanId,
    this.latestRunId,
    this.latestPlanAt,
    this.latestRunAt,
  });

  final int totalPlans;
  final int totalActivePlans;
  final int activePlans;
  final int readyForReviewCount;
  final int pendingAuthCount;
  final int authRequiredCount;
  final int blockedCount;
  final int blockedRunCount;
  final int prefillReadyCount;
  final int safeRunCompletedCount;
  final int failedCount;
  final int activeConversationCount;
  final int archivedConversationCount;
  final int todayMessagesCount;
  final String? latestConversationKey;
  final int? latestPlanId;
  final int? latestRunId;
  final DateTime? latestPlanAt;
  final DateTime? latestRunAt;

  factory AgentOperationsSummary.fromJson(Map<String, dynamic> json) {
    return AgentOperationsSummary(
      totalPlans: _readInt(json['total_plans']),
      totalActivePlans: _readInt(json['total_active_plans']),
      activePlans: _readInt(json['active_plans']),
      readyForReviewCount: _readInt(json['ready_for_review_count']),
      pendingAuthCount: _readInt(json['pending_auth_count']),
      authRequiredCount: _readInt(json['auth_required_count']),
      blockedCount: _readInt(json['blocked_count']),
      blockedRunCount: _readInt(json['blocked_run_count']),
      prefillReadyCount: _readInt(json['prefill_ready_count']),
      safeRunCompletedCount: _readInt(json['safe_run_completed_count']),
      failedCount: _readInt(json['failed_count']),
      activeConversationCount: _readInt(json['active_conversation_count']),
      archivedConversationCount: _readInt(json['archived_conversation_count']),
      todayMessagesCount: _readInt(json['today_messages_count']),
      latestConversationKey:
          _readNullableString(json['latest_conversation_key']),
      latestPlanId: _readNullableInt(json['latest_plan_id']),
      latestRunId: _readNullableInt(json['latest_run_id']),
      latestPlanAt: _readDate(json['latest_plan_at']),
      latestRunAt: _readDate(json['latest_run_at']),
    );
  }
}

class AgentOperationsSafety {
  const AgentOperationsSafety({
    this.readOnly = true,
    this.realOrderSubmitted = false,
    this.brokerSubmitCalled = false,
    this.manualSubmitCalled = false,
    this.validationCalled = false,
    this.settingChanged = false,
    this.schedulerChanged = false,
  });

  final bool readOnly;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool validationCalled;
  final bool settingChanged;
  final bool schedulerChanged;

  bool get noUnsafeAction =>
      readOnly &&
      !realOrderSubmitted &&
      !brokerSubmitCalled &&
      !manualSubmitCalled &&
      !validationCalled &&
      !settingChanged &&
      !schedulerChanged;

  factory AgentOperationsSafety.fromJson(Map<String, dynamic> json) {
    return AgentOperationsSafety(
      readOnly: json['read_only'] != false,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      validationCalled: json['validation_called'] == true,
      settingChanged: json['setting_changed'] == true,
      schedulerChanged: json['scheduler_changed'] == true,
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

int _readInt(Object? value) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? 0;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

DateTime? _readDate(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}
