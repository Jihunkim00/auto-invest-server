class KisManualOrderSafetyStatus {
  const KisManualOrderSafetyStatus({
    required this.runtimeDryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.marketOpen,
    required this.entryAllowedNow,
    required this.noNewEntryAfter,
  });

  factory KisManualOrderSafetyStatus.fromJson(Map<String, dynamic> json) {
    final marketSession =
        Map<String, dynamic>.from((json['market_session'] as Map?) ?? {});
    return KisManualOrderSafetyStatus(
      runtimeDryRun: json['runtime_dry_run'] == true || json['dry_run'] == true,
      killSwitch: json['kill_switch'] == true,
      kisEnabled: json['kis_enabled'] == true,
      kisRealOrderEnabled: json['kis_real_order_enabled'] == true,
      marketOpen: json['market_open'] == true ||
          marketSession['is_market_open'] == true,
      entryAllowedNow: json['entry_allowed_now'] == true ||
          marketSession['is_entry_allowed_now'] == true,
      noNewEntryAfter: _readString(
          json['no_new_entry_after'] ?? marketSession['no_new_entry_after'],
          '15:00'),
    );
  }

  final bool runtimeDryRun;
  final bool killSwitch;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final bool marketOpen;
  final bool entryAllowedNow;
  final String noNewEntryAfter;

  static const safeDefault = KisManualOrderSafetyStatus(
    runtimeDryRun: true,
    killSwitch: false,
    kisEnabled: false,
    kisRealOrderEnabled: false,
    marketOpen: false,
    entryAllowedNow: false,
    noNewEntryAfter: '15:00',
  );
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return fallback;
  return text;
}
