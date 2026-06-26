import 'strategy_profile.dart';

class AgentChatStrategyAction {
  const AgentChatStrategyAction({
    required this.actionId,
    required this.status,
    required this.requestedProfile,
    required this.actionType,
    this.conversationKey,
    this.currentProfile,
    this.expiresAt,
    this.confirmedAt,
    this.cancelledAt,
    this.requestedProfilePayload,
    this.activeProfile,
    this.safety = const {},
    this.raw = const {},
  });

  final int actionId;
  final String? conversationKey;
  final String actionType;
  final String requestedProfile;
  final String? currentProfile;
  final String status;
  final String? expiresAt;
  final String? confirmedAt;
  final String? cancelledAt;
  final StrategyProfile? requestedProfilePayload;
  final StrategyProfile? activeProfile;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> raw;

  bool get isPending => status == 'pending_confirmation';
  bool get isApplied => status == 'applied';
  bool get isCancelled => status == 'cancelled';
  bool get isAggressive => requestedProfile == 'aggressive';

  String get displayName =>
      requestedProfilePayload?.displayName ??
      strategyProfileLabel(requestedProfile);

  factory AgentChatStrategyAction.fromJson(Map<String, dynamic> json) {
    final requested = json['requested_profile_payload'];
    final active = json['active_profile'];
    return AgentChatStrategyAction(
      actionId: _readInt(json['action_id']),
      conversationKey: _readNullableString(json['conversation_key']),
      actionType: _readString(json['action_type'], 'strategy_profile_apply'),
      requestedProfile: _readString(json['requested_profile'], ''),
      currentProfile: _readNullableString(json['current_profile']),
      status: _readString(json['status'], 'pending_confirmation'),
      expiresAt: _readNullableString(json['expires_at']),
      confirmedAt: _readNullableString(json['confirmed_at']),
      cancelledAt: _readNullableString(json['cancelled_at']),
      requestedProfilePayload: requested is Map
          ? StrategyProfile.fromJson(Map<String, dynamic>.from(requested))
          : null,
      activeProfile: active is Map
          ? StrategyProfile.fromJson(Map<String, dynamic>.from(active))
          : null,
      safety: _readMap(json['safety']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AgentChatStrategyActionResponse {
  const AgentChatStrategyActionResponse({
    required this.status,
    required this.answer,
    required this.safety,
    required this.diagnostics,
    this.strategyAction,
    this.activeProfile,
    this.assistantMessageId,
  });

  final String status;
  final AgentChatStrategyActionAnswer answer;
  final AgentChatStrategyAction? strategyAction;
  final StrategyProfile? activeProfile;
  final Map<String, dynamic> safety;
  final int? assistantMessageId;
  final Map<String, dynamic> diagnostics;

  factory AgentChatStrategyActionResponse.fromJson(Map<String, dynamic> json) {
    final action = json['strategy_action'];
    final active = json['active_profile'];
    return AgentChatStrategyActionResponse(
      status: _readString(json['status'], ''),
      answer: AgentChatStrategyActionAnswer.fromJson(_readMap(json['answer'])),
      strategyAction: action is Map
          ? AgentChatStrategyAction.fromJson(Map<String, dynamic>.from(action))
          : null,
      activeProfile: active is Map
          ? StrategyProfile.fromJson(Map<String, dynamic>.from(active))
          : null,
      safety: _readMap(json['safety']),
      assistantMessageId: _readNullableInt(json['assistant_message_id']),
      diagnostics: _readMap(json['diagnostics']),
    );
  }
}

class AgentChatStrategyActionAnswer {
  const AgentChatStrategyActionAnswer({
    required this.text,
    required this.answerType,
    this.role = 'assistant',
  });

  final String role;
  final String text;
  final String answerType;

  factory AgentChatStrategyActionAnswer.fromJson(Map<String, dynamic> json) {
    return AgentChatStrategyActionAnswer(
      role: _readString(json['role'], 'assistant'),
      text: _readString(json['text'], ''),
      answerType: _readString(json['answer_type'], ''),
    );
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

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
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
