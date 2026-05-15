import 'dart:convert';

/// Formats API error messages for user-friendly display.
/// Handles HTTP 409 safety gate responses and HTTP 502 KIS read-only errors.
class ApiErrorFormatter {
  /// Formats an API error message.
  /// [errorMessage] is typically the toString() of an ApiRequestException.
  static String format(String errorMessage) {
    // Try to parse as HTTP error
    final httpMatch = RegExp(r'HTTP (\d+): (.+)').firstMatch(errorMessage);
    if (httpMatch != null) {
      final statusCode = int.parse(httpMatch.group(1)!);
      final body = httpMatch.group(2)!;

      try {
        final json = jsonDecode(body) as Map<String, dynamic>;

        final concise = _extractConciseMessage(json);
        if (concise != null) return concise;

        if (statusCode == 409) {
          return _formatSafetyGateError(json);
        } else if (statusCode == 502) {
          return _formatKisReadOnlyError(json);
        }
      } catch (_) {
        // Not JSON, fall through
      }
    }

    // Fallback: return original message
    return errorMessage;
  }

  static String? _extractConciseMessage(Map<String, dynamic> json) {
    for (final key in ['message', 'primary_message']) {
      final value = json[key];
      if (value is String && value.trim().isNotEmpty) {
        return value.trim();
      }
    }

    final detail = json['detail'];
    if (detail is Map) {
      final value = detail['message'];
      if (value is String && value.trim().isNotEmpty) {
        return value.trim();
      }
    }
    return null;
  }

  static String _formatSafetyGateError(Map<String, dynamic> json) {
    final internalStatus = json['internal_status'] as String?;
    if (internalStatus != 'REJECTED_BY_SAFETY_GATE') {
      return 'HTTP 409: ${jsonEncode(json)}';
    }

    final blockReasons =
        (json['block_reasons'] as List<dynamic>?)?.cast<String>() ?? [];
    final realOrderSubmitted = json['real_order_submitted'] as bool? ?? true;
    final closureName = json['closure_name'] as String?;

    final messages = <String>[];

    if (!realOrderSubmitted) {
      messages.add('No real order was submitted.');
    }

    // Map block reasons
    for (final reason in blockReasons) {
      switch (reason) {
        case 'market_closed':
          messages.add('Market is closed.');
          break;
        case 'today_is_holiday':
          if (closureName != null && closureName.isNotEmpty) {
            messages.add('Today is a holiday: $closureName.');
          } else {
            messages.add('Today is a holiday.');
          }
          break;
        case 'buy_entry_not_allowed_now':
          messages.add('Buy entry is not allowed now.');
          break;
        case 'sell_entry_not_allowed_now':
          messages.add('Sell entry is not allowed now.');
          break;
        case 'recent_dry_run_validation_missing':
          messages.add('Dry-run validation is missing.');
          break;
        case 'kill_switch_enabled':
          messages.add('Kill switch is enabled.');
          break;
        case 'kis_disabled':
          messages.add('KIS trading is disabled.');
          break;
        case 'kis_real_order_disabled':
          messages.add('KIS real-order submission is disabled.');
          break;
        case 'confirmation_required':
          messages.add('Live confirmation is required.');
          break;
        case 'dry_run_must_be_false':
          messages.add('Live submit requires dry_run=false.');
          break;
        default:
          messages.add(reason); // Keep unknown reasons as-is
      }
    }

    if (messages.isEmpty) {
      messages.add('Order blocked by safety gate.');
    }

    return messages.join(' ');
  }

  static String _formatKisReadOnlyError(Map<String, dynamic> json) {
    final detail = json['detail'] as Map<String, dynamic>?;
    if (detail == null) {
      return 'HTTP 502: ${jsonEncode(json)}';
    }

    final message = detail['message'] as String?;
    final details = detail['details'] as String?;
    final path = json['path'] as String?;
    final trId = json['tr_id'] as String?;

    final messages = <String>[];

    if (path != null && path.contains('inquire-balance')) {
      messages.add('KIS account check failed.');
      messages.add('Balance inquiry failed.');
      if (trId != null && trId.isNotEmpty) {
        messages.add('TR ID: $trId.');
      }
    } else {
      messages.add('KIS read-only error.');
      if (message != null && message.isNotEmpty) {
        messages.add(message);
      }
    }

    final msgCd = json['msg_cd'] as String?;
    final msg1 = json['msg1'] as String?;
    if (msgCd != null && msgCd.isNotEmpty) {
      messages.add('Code: $msgCd');
    }
    if (msg1 != null && msg1.isNotEmpty) {
      messages.add(msg1);
    }

    if (details != null && details.isNotEmpty && details != message) {
      messages.add(details);
    }

    return messages.join(' ');
  }
}
