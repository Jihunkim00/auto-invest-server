class SchedulerStatus {
  const SchedulerStatus({
    required this.runtimeSchedulerEnabled,
    required this.us,
    required this.kr,
  });

  factory SchedulerStatus.fromJson(Map<String, dynamic> json) {
    return SchedulerStatus(
      runtimeSchedulerEnabled: json['runtime_scheduler_enabled'] == true,
      us: MarketSchedulerStatus.fromJson(
          Map<String, dynamic>.from((json['US'] as Map?) ?? {})),
      kr: MarketSchedulerStatus.fromJson(
          Map<String, dynamic>.from((json['KR'] as Map?) ?? {})),
    );
  }

  factory SchedulerStatus.safeDefault() {
    return const SchedulerStatus(
      runtimeSchedulerEnabled: false,
      us: MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: [],
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: false,
        timezone: 'Asia/Seoul',
        slots: [],
        previewOnly: true,
        realOrdersAllowed: false,
      ),
    );
  }

  final bool runtimeSchedulerEnabled;
  final MarketSchedulerStatus us;
  final MarketSchedulerStatus kr;
}

class MarketSchedulerStatus {
  const MarketSchedulerStatus({
    required this.enabledForScheduler,
    required this.timezone,
    required this.slots,
    this.previewOnly = false,
    this.realOrdersAllowed = false,
  });

  factory MarketSchedulerStatus.fromJson(Map<String, dynamic> json) {
    return MarketSchedulerStatus(
      enabledForScheduler: json['enabled_for_scheduler'] == true,
      timezone: _readString(json['timezone'], ''),
      slots: _readSlots(json['slots']),
      previewOnly: json['preview_only'] == true,
      realOrdersAllowed: json['real_orders_allowed'] == true,
    );
  }

  final bool enabledForScheduler;
  final String timezone;
  final List<String> slots;
  final bool previewOnly;
  final bool realOrdersAllowed;
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

List<String> _readSlots(Object? value) {
  if (value is! List) return const [];
  return value.map((item) {
    if (item is Map) {
      final name = item['name']?.toString() ?? '';
      final time = item['time']?.toString() ?? '';
      if (name.isEmpty) return time;
      if (time.isEmpty) return name;
      return '$name $time';
    }
    return item.toString();
  }).where((item) => item.trim().isNotEmpty).toList();
}
