enum AgentChatRole {
  user,
  assistant,
  system,
  safety,
  error,
}

enum AgentChatStatus {
  pending,
  sent,
  parsing,
  planCreated,
  readyForReview,
  safeRunCompleted,
  prefillReady,
  authRequired,
  blocked,
  failed,
}

enum AgentChatPanelMode {
  collapsed,
  mini,
  expanded,
  fullscreen,
}

class AgentChatMessage {
  const AgentChatMessage({
    required this.id,
    required this.role,
    required this.text,
    required this.createdAt,
    required this.status,
    this.commandLogId,
    this.planId,
    this.runId,
    this.prefillAvailable = false,
    this.safetyBadges = const [],
    this.metadata = const {},
  });

  final String id;
  final AgentChatRole role;
  final String text;
  final DateTime createdAt;
  final AgentChatStatus status;
  final int? commandLogId;
  final int? planId;
  final int? runId;
  final bool prefillAvailable;
  final List<String> safetyBadges;
  final Map<String, dynamic> metadata;

  factory AgentChatMessage.fromJson(Map<String, dynamic> json) {
    return AgentChatMessage(
      id: _readString(json['id'], ''),
      role: agentChatRoleFromString(_readString(json['role'], 'assistant')),
      text: _readString(json['text'], ''),
      createdAt: DateTime.tryParse(_readString(json['created_at'], '')) ??
          DateTime.fromMillisecondsSinceEpoch(0),
      status: agentChatStatusFromString(_readString(json['status'], 'sent')),
      commandLogId: _readNullableInt(json['command_log_id']),
      planId: _readNullableInt(json['plan_id']),
      runId: _readNullableInt(json['run_id']),
      prefillAvailable: json['prefill_available'] == true,
      safetyBadges: _readStringList(json['safety_badges']),
      metadata: _readMap(json['metadata']),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'role': role.name,
      'text': text,
      'created_at': createdAt.toIso8601String(),
      'status': status.wireName,
      'command_log_id': commandLogId,
      'plan_id': planId,
      'run_id': runId,
      'prefill_available': prefillAvailable,
      'safety_badges': safetyBadges,
      'metadata': metadata,
    };
  }

  AgentChatMessage copyWith({
    AgentChatRole? role,
    String? text,
    AgentChatStatus? status,
    int? commandLogId,
    int? planId,
    int? runId,
    bool? prefillAvailable,
    List<String>? safetyBadges,
    Map<String, dynamic>? metadata,
  }) {
    return AgentChatMessage(
      id: id,
      role: role ?? this.role,
      text: text ?? this.text,
      createdAt: createdAt,
      status: status ?? this.status,
      commandLogId: commandLogId ?? this.commandLogId,
      planId: planId ?? this.planId,
      runId: runId ?? this.runId,
      prefillAvailable: prefillAvailable ?? this.prefillAvailable,
      safetyBadges: safetyBadges ?? this.safetyBadges,
      metadata: metadata ?? this.metadata,
    );
  }
}

extension AgentChatStatusWireName on AgentChatStatus {
  String get wireName {
    switch (this) {
      case AgentChatStatus.planCreated:
        return 'plan_created';
      case AgentChatStatus.readyForReview:
        return 'ready_for_review';
      case AgentChatStatus.safeRunCompleted:
        return 'safe_run_completed';
      case AgentChatStatus.prefillReady:
        return 'prefill_ready';
      case AgentChatStatus.authRequired:
        return 'auth_required';
      case AgentChatStatus.pending:
      case AgentChatStatus.sent:
      case AgentChatStatus.parsing:
      case AgentChatStatus.blocked:
      case AgentChatStatus.failed:
        return name;
    }
  }
}

AgentChatRole agentChatRoleFromString(String value) {
  switch (value.trim().toLowerCase()) {
    case 'user':
      return AgentChatRole.user;
    case 'system':
      return AgentChatRole.system;
    case 'safety':
      return AgentChatRole.safety;
    case 'error':
      return AgentChatRole.error;
    case 'assistant':
    case 'plan':
    default:
      return AgentChatRole.assistant;
  }
}

AgentChatStatus agentChatStatusFromString(String value) {
  switch (value.trim().toLowerCase()) {
    case 'pending':
      return AgentChatStatus.pending;
    case 'parsing':
      return AgentChatStatus.parsing;
    case 'plan_created':
      return AgentChatStatus.planCreated;
    case 'ready_for_review':
      return AgentChatStatus.readyForReview;
    case 'safe_run_completed':
      return AgentChatStatus.safeRunCompleted;
    case 'prefill_ready':
      return AgentChatStatus.prefillReady;
    case 'auth_required':
      return AgentChatStatus.authRequired;
    case 'blocked':
      return AgentChatStatus.blocked;
    case 'failed':
      return AgentChatStatus.failed;
    case 'sent':
    default:
      return AgentChatStatus.sent;
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return fallback;
  return text;
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
