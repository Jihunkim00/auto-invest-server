import 'agent_plan.dart';
import 'agent_run.dart';
import 'agent_chat_tool_result.dart';

class AgentChatSendResponse {
  const AgentChatSendResponse({
    required this.conversationKey,
    required this.intent,
    required this.answer,
    required this.data,
    required this.availableActions,
    required this.safety,
    required this.contextSnapshot,
    required this.selectedTools,
    required this.toolResults,
    required this.resultCards,
    required this.followUpSuggestions,
    required this.diagnostics,
    required this.fallbackUsed,
    this.userMessageId,
    this.assistantMessageId,
    this.command,
    this.plan,
    this.run,
    this.answerType,
  });

  final String conversationKey;
  final int? userMessageId;
  final int? assistantMessageId;
  final AgentChatIntent intent;
  final AgentChatAnswer answer;
  final Map<String, dynamic> data;
  final Map<String, dynamic>? command;
  final AgentPlan? plan;
  final AgentPlanRunResult? run;
  final List<String> availableActions;
  final AgentChatSafety safety;
  final Map<String, dynamic> contextSnapshot;
  final List<AgentChatToolCall> selectedTools;
  final List<AgentChatToolResult> toolResults;
  final List<AgentChatResultCard> resultCards;
  final List<String> followUpSuggestions;
  final Map<String, dynamic> diagnostics;
  final String? answerType;
  final bool fallbackUsed;

  factory AgentChatSendResponse.fromJson(Map<String, dynamic> json) {
    final planJson = json['plan'];
    final runJson = json['run'];
    final commandJson = json['command'];
    return AgentChatSendResponse(
      conversationKey: _readString(json['conversation_key'], ''),
      userMessageId: _readNullableInt(json['user_message_id']),
      assistantMessageId: _readNullableInt(json['assistant_message_id']),
      intent: AgentChatIntent.fromJson(_readMap(json['intent'])),
      answer: AgentChatAnswer.fromJson(_readMap(json['answer'])),
      data: _readMap(json['data']),
      command:
          commandJson is Map ? Map<String, dynamic>.from(commandJson) : null,
      plan: planJson is Map
          ? AgentPlan.fromJson(Map<String, dynamic>.from(planJson))
          : null,
      run: runJson is Map
          ? AgentPlanRunResult.fromJson(Map<String, dynamic>.from(runJson))
          : null,
      availableActions: _readStringList(json['available_actions']),
      safety: AgentChatSafety.fromJson(_readMap(json['safety'])),
      contextSnapshot: _readMap(json['context_snapshot']),
      selectedTools: _readToolCallList(json['selected_tools']),
      toolResults: _readToolResultList(json['tool_results']),
      resultCards: _readResultCardList(json['result_cards']),
      followUpSuggestions: _readStringList(json['follow_up_suggestions']),
      diagnostics: _readMap(json['diagnostics']),
      answerType: _readNullableString(json['answer_type']),
      fallbackUsed: json['fallback_used'] == true,
    );
  }
}

class AgentChatIntent {
  const AgentChatIntent({
    required this.category,
    required this.supported,
    required this.confidence,
    required this.side,
    required this.requiresPlan,
    required this.requiresAuth,
    required this.requiresManualConfirmation,
    required this.fallbackUsed,
    required this.parserStatus,
    required this.selectedTools,
    this.market,
    this.provider,
    this.symbol,
    this.symbolName,
    this.quantity,
    this.notional,
    this.currency,
    this.reason,
    this.modelName,
    this.raw = const {},
  });

  final String category;
  final bool supported;
  final double confidence;
  final String? market;
  final String? provider;
  final String? symbol;
  final String? symbolName;
  final String side;
  final double? quantity;
  final double? notional;
  final String? currency;
  final bool requiresPlan;
  final bool requiresAuth;
  final bool requiresManualConfirmation;
  final String? reason;
  final bool fallbackUsed;
  final String parserStatus;
  final String? modelName;
  final List<AgentChatToolCall> selectedTools;
  final Map<String, dynamic> raw;

  bool get isReadOnly => category.startsWith('read_only_');

  factory AgentChatIntent.fromJson(Map<String, dynamic> json) {
    return AgentChatIntent(
      category: _readString(json['category'], 'general_chat'),
      supported: json['supported'] != false,
      confidence: _readDouble(json['confidence'], 0),
      market: _readNullableString(json['market']),
      provider: _readNullableString(json['provider']),
      symbol: _readNullableString(json['symbol']),
      symbolName: _readNullableString(json['symbol_name']),
      side: _readString(json['side'], 'none'),
      quantity: _readNullableDouble(json['quantity']),
      notional: _readNullableDouble(json['notional']),
      currency: _readNullableString(json['currency']),
      requiresPlan: json['requires_plan'] == true,
      requiresAuth: json['requires_auth'] == true,
      requiresManualConfirmation: json['requires_manual_confirmation'] == true,
      reason: _readNullableString(json['reason']),
      fallbackUsed: json['fallback_used'] == true,
      parserStatus: _readString(json['parser_status'], ''),
      modelName: _readNullableString(json['model_name']),
      selectedTools: _readToolCallList(json['selected_tools']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AgentChatAnswer {
  const AgentChatAnswer({
    required this.role,
    required this.text,
    required this.answerType,
  });

  final String role;
  final String text;
  final String answerType;

  factory AgentChatAnswer.fromJson(Map<String, dynamic> json) {
    return AgentChatAnswer(
      role: _readString(json['role'], 'assistant'),
      text: _readString(json['text'], ''),
      answerType: _readString(json['answer_type'], 'general_answer'),
    );
  }
}

class AgentChatSafety {
  const AgentChatSafety({
    required this.readOnly,
    required this.safeExecutionOnly,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.validationCalled,
    required this.settingChanged,
    required this.schedulerChanged,
    required this.confirmLiveAutoChecked,
    required this.mutation,
    this.raw = const {},
  });

  final bool readOnly;
  final bool safeExecutionOnly;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool validationCalled;
  final bool settingChanged;
  final bool schedulerChanged;
  final bool confirmLiveAutoChecked;
  final bool mutation;
  final Map<String, dynamic> raw;

  factory AgentChatSafety.fromJson(Map<String, dynamic> json) {
    return AgentChatSafety(
      readOnly: json['read_only'] == true,
      safeExecutionOnly: json['safe_execution_only'] != false,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      validationCalled: json['validation_called'] == true,
      settingChanged: json['setting_changed'] == true,
      schedulerChanged: json['scheduler_changed'] == true,
      confirmLiveAutoChecked: json['confirm_live_auto_checked'] == true,
      mutation: json['mutation'] == true,
      raw: Map<String, dynamic>.from(json),
    );
  }
}

List<AgentChatToolCall> _readToolCallList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map)
        AgentChatToolCall.fromJson(Map<String, dynamic>.from(item)),
  ];
}

List<AgentChatToolResult> _readToolResultList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map)
        AgentChatToolResult.fromJson(Map<String, dynamic>.from(item)),
  ];
}

List<AgentChatResultCard> _readResultCardList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map)
        AgentChatResultCard.fromJson(Map<String, dynamic>.from(item)),
  ];
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

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

double _readDouble(Object? value, double fallback) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '') ?? fallback;
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  return double.tryParse(value.toString());
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}
