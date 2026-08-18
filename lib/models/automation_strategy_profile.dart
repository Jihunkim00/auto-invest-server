class AutomationStrategyProfile {
  const AutomationStrategyProfile({
    required this.id,
    required this.profileKey,
    required this.name,
    required this.provider,
    required this.market,
    required this.enabled,
    required this.status,
    required this.settings,
    this.raw = const {},
  });

  final int id;
  final String profileKey;
  final String name;
  final String provider;
  final String market;
  final bool enabled;
  final String status;
  final Map<String, dynamic> settings;
  final Map<String, dynamic> raw;

  Map<String, dynamic> get capital => _map(settings['capital']);
  Map<String, dynamic> get universe => _map(settings['universe']);
  Map<String, dynamic> get entry => _map(settings['entry']);
  Map<String, dynamic> get monitoring => _map(settings['monitoring']);
  Map<String, dynamic> get exit => _map(settings['exit']);
  Map<String, dynamic> get operation => _map(settings['operation']);
  int get maxOpenPositions => _int(settings['max_open_positions'], 1);
  bool get requiresPr109PortfolioEngine => maxOpenPositions > 1;
  bool get multiPositionExecutionSupported => false;

  factory AutomationStrategyProfile.fromJson(Map<String, dynamic> json) {
    return AutomationStrategyProfile(
      id: _int(json['id'], 0),
      profileKey: _string(json['profile_key']),
      name: _string(json['name'] ?? json['display_name']),
      provider: _string(json['provider'], 'kis'),
      market: _string(json['market'], 'KR'),
      enabled: json['enabled'] == true,
      status: _string(json['status'], 'disabled'),
      settings: _map(json['settings']),
      raw: Map<String, dynamic>.from(json),
    );
  }
}

class AutomationStrategyProfileList {
  const AutomationStrategyProfileList({required this.profiles, this.activeProfile});

  final List<AutomationStrategyProfile> profiles;
  final AutomationStrategyProfile? activeProfile;

  factory AutomationStrategyProfileList.fromJson(Map<String, dynamic> json) {
    final items = json['profiles'] is List ? json['profiles'] as List : const [];
    final profiles = [
      for (final item in items)
        if (item is Map)
          AutomationStrategyProfile.fromJson(Map<String, dynamic>.from(item)),
    ];
    final active = json['active_profile'];
    return AutomationStrategyProfileList(
      profiles: profiles,
      activeProfile: active is Map
          ? AutomationStrategyProfile.fromJson(Map<String, dynamic>.from(active))
          : null,
    );
  }
}

Map<String, dynamic> _map(Object? value) =>
    value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};

String _string(Object? value, [String fallback = '']) {
  final text = value?.toString().trim();
  return text == null || text.isEmpty ? fallback : text;
}

int _int(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}
