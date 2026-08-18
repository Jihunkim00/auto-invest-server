class AgentChatV2Response {
  const AgentChatV2Response({
    required this.intent,
    required this.status,
    required this.message,
    required this.symbol,
    required this.symbolName,
    required this.market,
    required this.action,
    required this.scores,
    required this.confidence,
    required this.risk,
    required this.analysis,
    required this.portfolio,
    required this.orderPreview,
    required this.requiresConfirmation,
    required this.availableActions,
    required this.resultCards,
    required this.followUpSuggestions,
    required this.contextSnapshot,
    required this.safety,
    required this.diagnostics,
    this.conversationKey,
    this.answer,
    this.data = const {},
    this.language = 'ko',
    this.gptUsed = false,
    this.fallbackUsed = false,
  });

  factory AgentChatV2Response.fromJson(Map<String, dynamic> json) {
    return AgentChatV2Response(
      intent: _readString(json['intent'], 'analyze'),
      status: _readString(json['status'], 'completed'),
      message: _readString(json['message'] ?? json['answer'], ''),
      answer: _readNullableString(json['answer']),
      language: _readString(json['language'], 'ko'),
      data: _readMap(json['data']),
      gptUsed: json['gpt_used'] == true,
      fallbackUsed: json['fallback_used'] == true,
      conversationKey: _readNullableString(json['conversation_key']),
      symbol: _readNullableString(json['symbol']),
      symbolName: _readNullableString(json['symbol_name']),
      market: _readNullableString(json['market']),
      action: _readNullableString(json['action']),
      scores: _readMap(json['scores']),
      confidence: _readNullableDouble(json['confidence']),
      risk: _readMap(json['risk']),
      analysis: _readMap(json['analysis']),
      portfolio: _readMap(json['portfolio']),
      orderPreview: json['order_preview'] is Map
          ? Map<String, dynamic>.from(json['order_preview'] as Map)
          : null,
      requiresConfirmation: json['requires_confirmation'] == true,
      availableActions: _readStringList(json['available_actions']),
      resultCards: _readMapList(json['result_cards']),
      followUpSuggestions: _readStringList(json['follow_up_suggestions']),
      contextSnapshot: _readMap(json['context_snapshot']),
      safety: _readMap(json['safety']),
      diagnostics: _readMap(json['diagnostics']),
    );
  }

  final String intent;
  final String status;
  final String message;
  final String? answer;
  final String language;
  final Map<String, dynamic> data;
  final bool gptUsed;
  final bool fallbackUsed;
  final String? conversationKey;
  final String? symbol;
  final String? symbolName;
  final String? market;
  final String? action;
  final Map<String, dynamic> scores;
  final double? confidence;
  final Map<String, dynamic> risk;
  final Map<String, dynamic> analysis;
  final Map<String, dynamic> portfolio;
  final Map<String, dynamic>? orderPreview;
  final bool requiresConfirmation;
  final List<String> availableActions;
  final List<Map<String, dynamic>> resultCards;
  final List<String> followUpSuggestions;
  final Map<String, dynamic> contextSnapshot;
  final Map<String, dynamic> safety;
  final Map<String, dynamic> diagnostics;

  bool get isError => status == 'error';
  bool get isBlocked => status == 'blocked';
  String get displayAnswer => answer ?? message;

  static Map<String, dynamic> _readMap(Object? value) {
    if (value is Map) return Map<String, dynamic>.from(value);
    return const {};
  }

  static List<Map<String, dynamic>> _readMapList(Object? value) {
    if (value is! List) return const [];
    return [
      for (final item in value)
        if (item is Map) Map<String, dynamic>.from(item),
    ];
  }

  static List<String> _readStringList(Object? value) {
    if (value is! List) return const [];
    return [
      for (final item in value)
        if (item != null && item.toString().trim().isNotEmpty)
          item.toString().trim(),
    ];
  }

  static String _readString(Object? value, String fallback) {
    final text = value?.toString().trim();
    return text == null || text.isEmpty ? fallback : text;
  }

  static String? _readNullableString(Object? value) {
    final text = value?.toString().trim();
    return text == null || text.isEmpty || text == 'null' ? null : text;
  }

  static double? _readNullableDouble(Object? value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }
}
