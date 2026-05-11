class KisManualOrderSafetyStatus {
  const KisManualOrderSafetyStatus({
    required this.runtimeDryRun,
    required this.killSwitch,
    required this.kisEnabled,
    required this.kisRealOrderEnabled,
    required this.marketOpen,
    required this.entryAllowedNow,
    required this.noNewEntryAfter,
    this.marketClosureReason,
    this.marketClosureName,
    this.effectiveClose,
    this.hasRuntimeDryRun = true,
    this.hasKillSwitch = true,
    this.hasKisEnabled = true,
    this.hasKisRealOrderEnabled = true,
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
      marketClosureReason: _readNullableString(marketSession['closure_reason']),
      marketClosureName: _readNullableString(marketSession['closure_name']),
      effectiveClose: _readNullableString(marketSession['effective_close']),
      hasRuntimeDryRun:
          json.containsKey('runtime_dry_run') || json.containsKey('dry_run'),
      hasKillSwitch: json.containsKey('kill_switch'),
      hasKisEnabled: json.containsKey('kis_enabled'),
      hasKisRealOrderEnabled: json.containsKey('kis_real_order_enabled'),
    );
  }

  final bool runtimeDryRun;
  final bool killSwitch;
  final bool kisEnabled;
  final bool kisRealOrderEnabled;
  final bool marketOpen;
  final bool entryAllowedNow;
  final String noNewEntryAfter;
  final String? marketClosureReason;
  final String? marketClosureName;
  final String? effectiveClose;
  final bool hasRuntimeDryRun;
  final bool hasKillSwitch;
  final bool hasKisEnabled;
  final bool hasKisRealOrderEnabled;

  static const safeDefault = KisManualOrderSafetyStatus(
    runtimeDryRun: true,
    killSwitch: false,
    kisEnabled: false,
    kisRealOrderEnabled: false,
    marketOpen: false,
    entryAllowedNow: false,
    noNewEntryAfter: '15:00',
    hasRuntimeDryRun: false,
    hasKillSwitch: false,
    hasKisEnabled: false,
    hasKisRealOrderEnabled: false,
  );
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty) return null;
  return text;
}
