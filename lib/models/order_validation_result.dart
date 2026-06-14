class OrderValidationResult {
  const OrderValidationResult({
    required this.provider,
    required this.market,
    required this.environment,
    required this.dryRun,
    required this.validatedForSubmission,
    required this.canSubmitLater,
    required this.symbol,
    required this.side,
    required this.qty,
    required this.orderType,
    required this.currentPrice,
    required this.estimatedAmount,
    required this.availableCash,
    required this.heldQty,
    required this.warnings,
    required this.blockReasons,
    required this.marketSession,
    required this.orderPreview,
    this.primaryBlockReason,
    this.message,
    this.detail = const {},
    this.sourceMetadata = const {},
    this.source,
    this.sourceType,
    this.exitTrigger,
    this.exitTriggerSource,
    this.companyName,
    this.estimatedPrice,
    this.estimatedNotional,
    this.runtimeDryRun,
    this.killSwitch,
    this.kisEnabled,
    this.kisRealOrderEnabled,
    this.marketOpen,
    this.entryAllowedNow,
    this.noNewEntryAfter,
    this.currentOperationMode,
    this.maxOrderNotionalPct,
    this.dailyLiveOrderRemaining,
    this.validatedAt,
    this.validationExpiresAt,
    this.warningLevel,
    this.riskFlags = const [],
    this.gatingNotes = const [],
    this.submitAllowed,
    this.confirmLiveRequired = true,
    this.manualOnly = true,
  });

  factory OrderValidationResult.fromJson(Map<String, dynamic> json) {
    final sourceMetadata =
        Map<String, dynamic>.from((json['source_metadata'] as Map?) ?? {});
    final validatedForSubmission = json['validated_for_submission'] == true;
    return OrderValidationResult(
      provider: _readString(json['provider'], ''),
      market: _readString(json['market'], ''),
      environment: _readString(json['environment'], ''),
      dryRun: json['dry_run'] == true,
      validatedForSubmission: validatedForSubmission,
      canSubmitLater: json['can_submit_later'] == true,
      symbol: _readString(json['symbol'], ''),
      side: _readString(json['side'], ''),
      qty: _readInt(json['qty'], 0),
      orderType: _readString(json['order_type'], ''),
      currentPrice:
          _readNullableDouble(json['current_price'] ?? json['estimated_price']),
      estimatedAmount: _readNullableDouble(
          json['estimated_amount'] ?? json['estimated_notional']),
      availableCash: _readNullableDouble(json['available_cash']),
      heldQty: _readNullableDouble(json['held_qty']),
      warnings: _readStringList(json['warnings']),
      blockReasons: _readStringList(json['block_reasons']),
      marketSession: MarketSessionStatus.fromJson(
          Map<String, dynamic>.from((json['market_session'] as Map?) ?? {})),
      orderPreview: OrderPreview.fromJson(
          Map<String, dynamic>.from((json['order_preview'] as Map?) ?? {})),
      primaryBlockReason: _readNullableString(json['primary_block_reason']),
      message: _readNullableString(json['message']),
      detail: Map<String, dynamic>.from((json['detail'] as Map?) ?? {}),
      sourceMetadata: sourceMetadata,
      source: _readNullableString(json['source']),
      sourceType: _readNullableString(json['source_type']),
      exitTrigger: _readNullableString(json['exit_trigger']),
      exitTriggerSource: _readNullableString(json['exit_trigger_source']),
      companyName: _readNullableString(
        json['company_name'] ??
            json['companyName'] ??
            json['name'] ??
            json['company'] ??
            json['asset_name'] ??
            sourceMetadata['company_name'] ??
            sourceMetadata['companyName'] ??
            sourceMetadata['name'] ??
            sourceMetadata['company'] ??
            sourceMetadata['asset_name'],
      ),
      estimatedPrice:
          _readNullableDouble(json['estimated_price'] ?? json['current_price']),
      estimatedNotional: _readNullableDouble(
          json['estimated_notional'] ?? json['estimated_amount']),
      runtimeDryRun: _readNullableBool(json['runtime_dry_run']),
      killSwitch: _readNullableBool(json['kill_switch']),
      kisEnabled: _readNullableBool(json['kis_enabled']),
      kisRealOrderEnabled: _readNullableBool(json['kis_real_order_enabled']),
      marketOpen: _readNullableBool(json['market_open']),
      entryAllowedNow: _readNullableBool(json['entry_allowed_now']),
      noNewEntryAfter: _readNullableString(json['no_new_entry_after']),
      currentOperationMode: _readNullableString(json['current_operation_mode']),
      maxOrderNotionalPct: _readNullableDouble(json['max_order_notional_pct']),
      dailyLiveOrderRemaining:
          _readNullableInt(json['daily_live_order_remaining']),
      validatedAt: _readNullableString(json['validated_at']),
      validationExpiresAt: _readNullableString(json['validation_expires_at']),
      warningLevel: _readNullableString(json['warning_level']),
      riskFlags: _readStringList(json['risk_flags']),
      gatingNotes: _readStringList(json['gating_notes']),
      submitAllowed:
          _readNullableBool(json['submit_allowed']) ?? validatedForSubmission,
      confirmLiveRequired:
          _readNullableBool(json['confirm_live_required']) ?? true,
      manualOnly: _readNullableBool(json['manual_only']) ?? true,
    );
  }

  final String provider;
  final String market;
  final String environment;
  final bool dryRun;
  final bool validatedForSubmission;
  final bool canSubmitLater;
  final String symbol;
  final String side;
  final int qty;
  final String orderType;
  final double? currentPrice;
  final double? estimatedAmount;
  final double? availableCash;
  final double? heldQty;
  final List<String> warnings;
  final List<String> blockReasons;
  final MarketSessionStatus marketSession;
  final OrderPreview orderPreview;
  final String? primaryBlockReason;
  final String? message;
  final Map<String, dynamic> detail;
  final Map<String, dynamic> sourceMetadata;
  final String? source;
  final String? sourceType;
  final String? exitTrigger;
  final String? exitTriggerSource;
  final String? companyName;
  final double? estimatedPrice;
  final double? estimatedNotional;
  final bool? runtimeDryRun;
  final bool? killSwitch;
  final bool? kisEnabled;
  final bool? kisRealOrderEnabled;
  final bool? marketOpen;
  final bool? entryAllowedNow;
  final String? noNewEntryAfter;
  final String? currentOperationMode;
  final double? maxOrderNotionalPct;
  final int? dailyLiveOrderRemaining;
  final String? validatedAt;
  final String? validationExpiresAt;
  final String? warningLevel;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final bool? submitAllowed;
  final bool confirmLiveRequired;
  final bool manualOnly;

  bool get isFromExitPreflight => source == 'kis_live_exit_preflight';

  bool get effectiveSubmitAllowed => submitAllowed ?? validatedForSubmission;

  DateTime? get validationExpiresAtTime => _parseTimestamp(validationExpiresAt);

  DateTime? get validatedAtTime => _parseTimestamp(validatedAt);

  bool get hasValidationExpiry => validationExpiresAtTime != null;

  bool get isValidationExpired {
    final expiresAt = validationExpiresAtTime;
    if (expiresAt == null) return false;
    return !DateTime.now().toUtc().isBefore(expiresAt.toUtc());
  }

  String get validationFreshnessLabel {
    if (isValidationExpired) return 'Validation expired, validate again';
    final validated = validatedAtTime;
    if (validated == null) return 'Validated just now';
    final age = DateTime.now().toUtc().difference(validated.toUtc());
    if (age.inMinutes < 1) return 'Validated just now';
    if (age.inMinutes == 1) return 'Validated 1 minute ago';
    return 'Validated ${age.inMinutes} minutes ago';
  }
}

class MarketSessionStatus {
  const MarketSessionStatus({
    required this.market,
    required this.timezone,
    required this.isMarketOpen,
    required this.isEntryAllowedNow,
    required this.isNearClose,
    this.closureReason,
    this.closureName,
    this.effectiveClose,
    this.noNewEntryAfter,
  });

  factory MarketSessionStatus.fromJson(Map<String, dynamic> json) {
    return MarketSessionStatus(
      market: _readString(json['market'], ''),
      timezone: _readString(json['timezone'], ''),
      isMarketOpen: json['is_market_open'] == true,
      isEntryAllowedNow: json['is_entry_allowed_now'] == true,
      isNearClose: json['is_near_close'] == true,
      closureReason: _readNullableString(json['closure_reason']),
      closureName: _readNullableString(json['closure_name']),
      effectiveClose: _readNullableString(json['effective_close']),
      noNewEntryAfter: _readNullableString(json['no_new_entry_after']),
    );
  }

  final String market;
  final String timezone;
  final bool isMarketOpen;
  final bool isEntryAllowedNow;
  final bool isNearClose;
  final String? closureReason;
  final String? closureName;
  final String? effectiveClose;
  final String? noNewEntryAfter;
}

class OrderPreview {
  const OrderPreview({
    required this.accountNoMasked,
    required this.productCode,
    required this.symbol,
    required this.side,
    required this.qty,
    required this.orderType,
    required this.kisTrIdPreview,
    required this.payloadPreview,
  });

  factory OrderPreview.fromJson(Map<String, dynamic> json) {
    return OrderPreview(
      accountNoMasked: _readString(json['account_no_masked'], ''),
      productCode: _readString(json['product_code'], ''),
      symbol: _readString(json['symbol'], ''),
      side: _readString(json['side'], ''),
      qty: _readInt(json['qty'], 0),
      orderType: _readString(json['order_type'], ''),
      kisTrIdPreview: _readString(json['kis_tr_id_preview'], ''),
      payloadPreview:
          Map<String, dynamic>.from((json['payload_preview'] as Map?) ?? {}),
    );
  }

  final String accountNoMasked;
  final String productCode;
  final String symbol;
  final String side;
  final int qty;
  final String orderType;
  final String kisTrIdPreview;
  final Map<String, dynamic> payloadPreview;
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

int? _readNullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString());
}

double? _readNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}

String? _readNullableString(Object? value) {
  final raw = value?.toString();
  if (raw == null) return null;
  final text = raw.trim();
  if (text.isEmpty) return null;
  return text;
}

bool? _readNullableBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes' || text == 'on') {
    return true;
  }
  if (text == 'false' || text == '0' || text == 'no' || text == 'off') {
    return false;
  }
  return null;
}

DateTime? _parseTimestamp(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return null;
  return DateTime.tryParse(text);
}

List<String> _readStringList(Object? value) {
  if (value is! List) return const [];
  return value.map((item) => item.toString()).toList();
}
