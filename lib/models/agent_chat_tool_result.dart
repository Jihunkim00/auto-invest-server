class AgentChatToolCall {
  const AgentChatToolCall({
    required this.toolName,
    required this.arguments,
    this.reason,
  });

  final String toolName;
  final Map<String, dynamic> arguments;
  final String? reason;

  factory AgentChatToolCall.fromJson(Map<String, dynamic> json) {
    return AgentChatToolCall(
      toolName: _readString(json['tool_name'], ''),
      arguments: _readMap(json['arguments']),
      reason: _readNullableString(json['reason']),
    );
  }
}

class AgentChatToolResult {
  const AgentChatToolResult({
    required this.toolName,
    required this.status,
    required this.resultType,
    required this.data,
    required this.summary,
    required this.safety,
    this.errorMessage,
  });

  final String toolName;
  final String status;
  final String resultType;
  final Map<String, dynamic> data;
  final String summary;
  final String? errorMessage;
  final AgentChatToolSafety safety;

  bool get isSuccess => status == 'success';
  bool get isBlocked => status == 'blocked';

  factory AgentChatToolResult.fromJson(Map<String, dynamic> json) {
    return AgentChatToolResult(
      toolName: _readString(json['tool_name'], ''),
      status: _readString(json['status'], 'unsupported'),
      resultType: _readString(json['result_type'], 'unsupported'),
      data: _readMap(json['data']),
      summary: _readString(json['summary'], ''),
      errorMessage: _readNullableString(json['error_message']),
      safety: AgentChatToolSafety.fromJson(_readMap(json['safety'])),
    );
  }
}

class AgentChatToolSafety {
  const AgentChatToolSafety({
    required this.readOnly,
    required this.mutation,
    required this.realOrderSubmitted,
    required this.brokerSubmitCalled,
    required this.manualSubmitCalled,
    required this.validationCalled,
    required this.settingChanged,
    required this.schedulerChanged,
    required this.confirmLiveAutoChecked,
    this.raw = const {},
  });

  final bool readOnly;
  final bool mutation;
  final bool realOrderSubmitted;
  final bool brokerSubmitCalled;
  final bool manualSubmitCalled;
  final bool validationCalled;
  final bool settingChanged;
  final bool schedulerChanged;
  final bool confirmLiveAutoChecked;
  final Map<String, dynamic> raw;

  factory AgentChatToolSafety.fromJson(Map<String, dynamic> json) {
    return AgentChatToolSafety(
      readOnly: json['read_only'] != false,
      mutation: json['mutation'] == true,
      realOrderSubmitted: json['real_order_submitted'] == true,
      brokerSubmitCalled: json['broker_submit_called'] == true,
      manualSubmitCalled: json['manual_submit_called'] == true,
      validationCalled: json['validation_called'] == true,
      settingChanged: json['setting_changed'] == true,
      schedulerChanged: json['scheduler_changed'] == true,
      confirmLiveAutoChecked: json['confirm_live_auto_checked'] == true,
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AgentChatResultCard {
  const AgentChatResultCard({
    required this.cardType,
    required this.title,
    required this.badges,
    required this.rows,
    required this.data,
    this.subtitle,
    this.primaryValue,
  });

  final String cardType;
  final String title;
  final String? subtitle;
  final String? primaryValue;
  final List<String> badges;
  final List<Map<String, dynamic>> rows;
  final Map<String, dynamic> data;

  factory AgentChatResultCard.fromJson(Map<String, dynamic> json) {
    return AgentChatResultCard(
      cardType: _readString(json['card_type'], 'generic'),
      title: _readString(json['title'], 'Result'),
      subtitle: _readNullableString(json['subtitle']),
      primaryValue: _readNullableString(json['primary_value']),
      badges: _readStringList(json['badges']),
      rows: _readMapList(json['rows']),
      data: _readMap(json['data']),
    );
  }
}

Map<String, dynamic> _readMap(Object? value) {
  if (value is Map) return Map<String, dynamic>.from(value);
  return const {};
}

List<Map<String, dynamic>> _readMapList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item is Map) Map<String, dynamic>.from(item),
  ];
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

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (item?.toString().trim().isNotEmpty == true) item.toString().trim(),
  ];
}
