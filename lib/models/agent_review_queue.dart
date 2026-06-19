class AgentReviewQueue {
  const AgentReviewQueue({
    required this.count,
    required this.items,
    required this.safety,
  });

  final int count;
  final List<AgentReviewQueueItem> items;
  final Map<String, dynamic> safety;

  factory AgentReviewQueue.fromJson(Map<String, dynamic> json) {
    final rawItems = json['items'] as List<dynamic>? ?? const [];
    return AgentReviewQueue(
      count: _readInt(json['count'], rawItems.length),
      items: rawItems
          .whereType<Map>()
          .map((item) => AgentReviewQueueItem.fromJson(
                Map<String, dynamic>.from(item),
              ))
          .toList(),
      safety: _readMap(json['safety']),
    );
  }

  static const empty = AgentReviewQueue(
    count: 0,
    items: [],
    safety: {'read_only': true},
  );
}

class AgentReviewQueueItem {
  const AgentReviewQueueItem({
    required this.queueId,
    required this.queueKey,
    required this.itemType,
    required this.queueType,
    required this.priority,
    required this.reviewStatus,
    required this.title,
    required this.summary,
    required this.safetyBadges,
    required this.canRunSafeAction,
    required this.canPrepareTicket,
    required this.metadata,
    this.reviewerNote,
    this.conversationKey,
    this.commandLogId,
    this.planId,
    this.planRunId,
    this.authApprovalRequestId,
    this.commandType,
    this.domain,
    this.market,
    this.provider,
    this.symbol,
    this.side,
    this.riskLevel,
    this.status,
    this.blockedReason,
    this.createdAt,
    this.updatedAt,
  });

  final String queueId;
  final String queueKey;
  final String itemType;
  final String queueType;
  final String priority;
  final String reviewStatus;
  final String? reviewerNote;
  final String? conversationKey;
  final int? commandLogId;
  final int? planId;
  final int? planRunId;
  final int? authApprovalRequestId;
  final String? commandType;
  final String? domain;
  final String? market;
  final String? provider;
  final String? symbol;
  final String? side;
  final String? riskLevel;
  final String? status;
  final String title;
  final String summary;
  final String? blockedReason;
  final List<String> safetyBadges;
  final bool canRunSafeAction;
  final bool canPrepareTicket;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final Map<String, dynamic> metadata;

  bool get canOpenChat =>
      conversationKey != null && conversationKey!.isNotEmpty;
  bool get isAuthRequired => queueType == 'auth_required';
  bool get isBlocked => queueType == 'blocked';

  factory AgentReviewQueueItem.fromJson(Map<String, dynamic> json) {
    return AgentReviewQueueItem(
      queueId: _readString(json['queue_id'], ''),
      queueKey:
          _readString(json['queue_key'], _readString(json['queue_id'], '')),
      itemType: _readString(json['item_type'], 'unknown'),
      queueType: _readString(json['queue_type'], 'all'),
      priority: _readString(json['priority'], 'low'),
      reviewStatus: _readString(json['review_status'], 'open'),
      reviewerNote: _readNullableString(json['reviewer_note']),
      conversationKey: _readNullableString(json['conversation_key']),
      commandLogId: _readNullableInt(json['command_log_id']),
      planId: _readNullableInt(json['plan_id']),
      planRunId: _readNullableInt(json['plan_run_id']),
      authApprovalRequestId: _readNullableInt(json['auth_approval_request_id']),
      commandType: _readNullableString(json['command_type']),
      domain: _readNullableString(json['domain']),
      market: _readNullableString(json['market']),
      provider: _readNullableString(json['provider']),
      symbol: _readNullableString(json['symbol']),
      side: _readNullableString(json['side']),
      riskLevel: _readNullableString(json['risk_level']),
      status: _readNullableString(json['status']),
      title: _readString(json['title'], 'Agent review item'),
      summary: _readString(json['summary'], ''),
      blockedReason: _readNullableString(json['blocked_reason']),
      safetyBadges: _readStringList(json['safety_badges']),
      canRunSafeAction: json['can_run_safe_action'] == true,
      canPrepareTicket: json['can_prepare_ticket'] == true,
      createdAt: _readDate(json['created_at']),
      updatedAt: _readDate(json['updated_at']),
      metadata: _readMap(json['metadata']),
    );
  }
}

class AgentReviewQueueStateResult {
  const AgentReviewQueueStateResult({
    required this.queueKey,
    required this.status,
    this.reviewerNote,
  });

  final String queueKey;
  final String status;
  final String? reviewerNote;

  factory AgentReviewQueueStateResult.fromJson(Map<String, dynamic> json) {
    final state = _readMap(json['state']);
    return AgentReviewQueueStateResult(
      queueKey: _readString(state['queue_key'], ''),
      status: _readString(state['status'], ''),
      reviewerNote: _readNullableString(state['reviewer_note']),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
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

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}

DateTime? _readDate(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}
