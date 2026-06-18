class AgentChatConversation {
  const AgentChatConversation({
    required this.id,
    required this.conversationKey,
    required this.status,
    required this.source,
    required this.metadata,
    this.title,
    this.createdAt,
    this.updatedAt,
    this.archivedAt,
    this.lastMessageAt,
  });

  final int id;
  final String conversationKey;
  final String? title;
  final String status;
  final String source;
  final Map<String, dynamic> metadata;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? archivedAt;
  final DateTime? lastMessageAt;

  factory AgentChatConversation.fromJson(Map<String, dynamic> json) {
    return AgentChatConversation(
      id: _readInt(json['id'], 0),
      conversationKey: _readString(json['conversation_key'], ''),
      title: _readNullableString(json['title']),
      status: _readString(json['status'], 'active'),
      source: _readString(json['source'], 'unknown'),
      metadata: _readMap(json['metadata']),
      createdAt: _readDate(json['created_at']),
      updatedAt: _readDate(json['updated_at']),
      archivedAt: _readDate(json['archived_at']),
      lastMessageAt: _readDate(json['last_message_at']),
    );
  }
}

class AgentChatConversationList {
  const AgentChatConversationList({
    required this.count,
    required this.conversations,
  });

  final int count;
  final List<AgentChatConversation> conversations;

  factory AgentChatConversationList.fromJson(Map<String, dynamic> json) {
    final items = json['conversations'] as List<dynamic>? ?? const [];
    return AgentChatConversationList(
      count: _readInt(json['count'], items.length),
      conversations: items
          .whereType<Map>()
          .map((item) =>
              AgentChatConversation.fromJson(Map<String, dynamic>.from(item)))
          .toList(),
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

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

DateTime? _readDate(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return DateTime.tryParse(text);
}
