const _kstOffset = Duration(hours: 9);

final _timestampPattern = RegExp(
  r'^\s*(?:(\d{4})-)?(\d{2})-(\d{2})[T\s](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:\s*(Z|[+-]\d{2}:?\d{2}))?\s*$',
);

String formatTimestampWithKst(String? value, {String fallback = '-'}) {
  final raw = value?.trim() ?? '';
  if (raw.isEmpty || raw == 'null') return fallback;

  final parsed = _ParsedTimestamp.tryParse(raw);
  if (parsed == null) return raw;

  final kst = parsed.utc.add(_kstOffset);
  return '${parsed.originalDisplay} (KST ${_twoDigits(kst.hour)}:${_twoDigits(kst.minute)})';
}

class _ParsedTimestamp {
  const _ParsedTimestamp({
    required this.month,
    required this.day,
    required this.hour,
    required this.minute,
    required this.utc,
  });

  final int month;
  final int day;
  final int hour;
  final int minute;
  final DateTime utc;

  String get originalDisplay {
    return '${_twoDigits(month)}-${_twoDigits(day)} '
        '${_twoDigits(hour)}:${_twoDigits(minute)}';
  }

  static _ParsedTimestamp? tryParse(String raw) {
    final match = _timestampPattern.firstMatch(raw);
    if (match == null) return null;

    final year = int.tryParse(match.group(1) ?? '2000');
    final month = int.tryParse(match.group(2) ?? '');
    final day = int.tryParse(match.group(3) ?? '');
    final hour = int.tryParse(match.group(4) ?? '');
    final minute = int.tryParse(match.group(5) ?? '');
    final second = int.tryParse(match.group(6) ?? '0');
    if (year == null ||
        month == null ||
        day == null ||
        hour == null ||
        minute == null ||
        second == null) {
      return null;
    }
    if (!_hasValidComponents(year, month, day, hour, minute, second)) {
      return null;
    }

    final sourceDateTime = DateTime.utc(
      year,
      month,
      day,
      hour,
      minute,
      second,
    );
    final zone = match.group(7);
    final offset = _offsetDuration(zone);
    if (offset == null) return null;

    return _ParsedTimestamp(
      month: month,
      day: day,
      hour: hour,
      minute: minute,
      utc: sourceDateTime.subtract(offset),
    );
  }
}

bool _hasValidComponents(
  int year,
  int month,
  int day,
  int hour,
  int minute,
  int second,
) {
  if (hour < 0 || hour > 23) return false;
  if (minute < 0 || minute > 59) return false;
  if (second < 0 || second > 59) return false;

  final date = DateTime.utc(year, month, day, hour, minute, second);
  return date.year == year &&
      date.month == month &&
      date.day == day &&
      date.hour == hour &&
      date.minute == minute &&
      date.second == second;
}

Duration? _offsetDuration(String? zone) {
  if (zone == null || zone == 'Z') return Duration.zero;

  final compact = zone.replaceAll(':', '');
  if (compact.length != 5) return null;

  final sign = compact.startsWith('-') ? -1 : 1;
  if (!compact.startsWith('-') && !compact.startsWith('+')) return null;

  final hours = int.tryParse(compact.substring(1, 3));
  final minutes = int.tryParse(compact.substring(3, 5));
  if (hours == null || minutes == null || hours > 23 || minutes > 59) {
    return null;
  }

  return Duration(minutes: sign * ((hours * 60) + minutes));
}

String _twoDigits(int value) => value.toString().padLeft(2, '0');
