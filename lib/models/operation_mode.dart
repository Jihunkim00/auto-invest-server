class OperationModeReason {
  const OperationModeReason({
    required this.code,
    required this.message,
  });

  final String code;
  final String message;

  factory OperationModeReason.fromJson(Object? value) {
    if (value is Map) {
      final json = Map<String, dynamic>.from(value);
      final code = _string(json['code'], 'unknown');
      return OperationModeReason(
        code: code,
        message: _string(json['message'], code),
      );
    }
    final text = _nullableString(value) ?? 'unknown';
    return OperationModeReason(code: text, message: text);
  }
}

class OperationModeStatus {
  const OperationModeStatus({
    required this.requestedMode,
    required this.effectiveMode,
    required this.displayLabel,
    required this.status,
    required this.safetyStatus,
    required this.canChangeMode,
    required this.canEnterPaper,
    required this.canEnterLive,
    required this.canEnterPaused,
    required this.requiresAcknowledgement,
    required this.modeDriftDetected,
    required this.blockingReasons,
    required this.warnings,
    required this.underlyingState,
    this.lastChangedAt,
    this.lastChangedBy,
  });

  static const safeDefault = OperationModeStatus(
    requestedMode: 'paper',
    effectiveMode: 'paper',
    displayLabel: 'Paper',
    status: 'active',
    safetyStatus: 'paper',
    canChangeMode: true,
    canEnterPaper: true,
    canEnterLive: false,
    canEnterPaused: true,
    requiresAcknowledgement: <String, bool>{'live': true},
    modeDriftDetected: false,
    blockingReasons: <OperationModeReason>[],
    warnings: <OperationModeReason>[],
    underlyingState: <String, dynamic>{},
  );

  final String requestedMode;
  final String effectiveMode;
  final String displayLabel;
  final String status;
  final String safetyStatus;
  final bool canChangeMode;
  final bool canEnterPaper;
  final bool canEnterLive;
  final bool canEnterPaused;
  final Map<String, bool> requiresAcknowledgement;
  final bool modeDriftDetected;
  final List<OperationModeReason> blockingReasons;
  final List<OperationModeReason> warnings;
  final Map<String, dynamic> underlyingState;
  final String? lastChangedAt;
  final String? lastChangedBy;

  bool get isLive => effectiveMode == 'live';
  bool get isBlocked => status == 'blocked' || safetyStatus == 'blocked';

  bool canEnter(String mode) {
    if (!canChangeMode) return false;
    switch (normalizeMode(mode)) {
      case 'live':
        return canEnterLive;
      case 'paused':
        return canEnterPaused;
      case 'paper':
        return canEnterPaper;
    }
    return false;
  }

  bool requiresAcknowledgementFor(String mode) {
    return requiresAcknowledgement[normalizeMode(mode)] ?? false;
  }

  factory OperationModeStatus.fromJson(Map<String, dynamic> json) {
    final requestedMode = normalizeMode(json['requested_mode']);
    final effectiveMode =
        normalizeMode(json['effective_mode'] ?? requestedMode);
    return OperationModeStatus(
      requestedMode: requestedMode,
      effectiveMode: effectiveMode,
      displayLabel:
          _string(json['display_label'], _displayLabelForMode(effectiveMode)),
      status: _string(json['status'], 'active'),
      safetyStatus: _string(json['safety_status'], effectiveMode),
      canChangeMode: _bool(json['can_change_mode']) ?? true,
      canEnterPaper: _bool(json['can_enter_paper']) ?? true,
      canEnterLive: _bool(json['can_enter_live']) ?? false,
      canEnterPaused: _bool(json['can_enter_paused']) ?? true,
      requiresAcknowledgement: _boolMap(json['requires_acknowledgement']),
      modeDriftDetected: _bool(json['mode_drift_detected']) ?? false,
      blockingReasons: _reasons(json['blocking_reasons']),
      warnings: _reasons(json['warnings']),
      underlyingState: _map(json['underlying_state']),
      lastChangedAt: _nullableString(json['last_changed_at']),
      lastChangedBy: _nullableString(json['last_changed_by']),
    );
  }

  static String normalizeMode(Object? value) {
    final text = value?.toString().trim().toLowerCase();
    return switch (text) {
      'live' => 'live',
      'paused' => 'paused',
      'paper' => 'paper',
      _ => 'paper',
    };
  }

  static String _displayLabelForMode(String mode) {
    return switch (normalizeMode(mode)) {
      'live' => 'Live',
      'paused' => 'Paused',
      _ => 'Paper',
    };
  }
}

class OperationModeChangeResult {
  const OperationModeChangeResult({
    required this.changed,
    required this.previousMode,
    required this.requestedMode,
    required this.effectiveMode,
    required this.status,
    required this.safetyStatus,
    required this.displayLabel,
    required this.message,
    required this.blockingReasons,
    required this.warnings,
    required this.underlyingState,
    this.auditId,
    this.changedAt,
  });

  final bool changed;
  final String previousMode;
  final String requestedMode;
  final String effectiveMode;
  final String status;
  final String safetyStatus;
  final String displayLabel;
  final String message;
  final List<OperationModeReason> blockingReasons;
  final List<OperationModeReason> warnings;
  final int? auditId;
  final String? changedAt;
  final Map<String, dynamic> underlyingState;

  bool get isBlocked => status == 'blocked' || safetyStatus == 'blocked';

  factory OperationModeChangeResult.fromJson(Map<String, dynamic> json) {
    final requestedMode = OperationModeStatus.normalizeMode(
      json['requested_mode'],
    );
    final effectiveMode = OperationModeStatus.normalizeMode(
      json['effective_mode'] ?? requestedMode,
    );
    return OperationModeChangeResult(
      changed: _bool(json['changed']) ?? false,
      previousMode: OperationModeStatus.normalizeMode(json['previous_mode']),
      requestedMode: requestedMode,
      effectiveMode: effectiveMode,
      status: _string(json['status'], 'active'),
      safetyStatus: _string(json['safety_status'], effectiveMode),
      displayLabel: _string(
        json['display_label'],
        OperationModeStatus._displayLabelForMode(effectiveMode),
      ),
      message: _string(json['message'], 'Operation mode updated.'),
      blockingReasons: _reasons(json['blocking_reasons']),
      warnings: _reasons(json['warnings']),
      auditId: _nullableInt(json['audit_id']),
      changedAt: _nullableString(json['changed_at']),
      underlyingState: _map(json['underlying_state']),
    );
  }

  OperationModeStatus toStatus({OperationModeStatus? fallback}) {
    final base = fallback ?? OperationModeStatus.safeDefault;
    return OperationModeStatus(
      requestedMode: requestedMode,
      effectiveMode: effectiveMode,
      displayLabel: displayLabel,
      status: status,
      safetyStatus: safetyStatus,
      canChangeMode: base.canChangeMode,
      canEnterPaper: base.canEnterPaper,
      canEnterLive: base.canEnterLive,
      canEnterPaused: base.canEnterPaused,
      requiresAcknowledgement: base.requiresAcknowledgement,
      modeDriftDetected: requestedMode != effectiveMode,
      blockingReasons: blockingReasons,
      warnings: warnings,
      underlyingState: underlyingState,
      lastChangedAt: changedAt ?? base.lastChangedAt,
      lastChangedBy: base.lastChangedBy,
    );
  }
}

int? _nullableInt(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toInt();
  return int.tryParse(value.toString().trim());
}

String _string(Object? value, String fallback) {
  return _nullableString(value) ?? fallback;
}

String? _nullableString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text;
}

bool? _bool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

Map<String, dynamic> _map(Object? value) {
  return value is Map
      ? Map<String, dynamic>.unmodifiable(Map<String, dynamic>.from(value))
      : const <String, dynamic>{};
}

Map<String, bool> _boolMap(Object? value) {
  if (value is! Map) return const <String, bool>{'live': true};
  return Map<String, bool>.unmodifiable({
    for (final entry in value.entries)
      entry.key.toString(): _bool(entry.value) ?? false,
  });
}

List<OperationModeReason> _reasons(Object? value) {
  if (value is! List) return const <OperationModeReason>[];
  return List<OperationModeReason>.unmodifiable([
    for (final item in value) OperationModeReason.fromJson(item),
  ]);
}
