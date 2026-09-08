import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/utils/timestamp_formatter.dart';

void main() {
  test('formats UTC-like backend timestamps with Korea time', () {
    expect(
      formatTimestampWithKst('2026-05-09T10:51:00'),
      '05-09 10:51 (KST 19:51)',
    );
    expect(
      formatTimestampWithKst('05-09T10:51'),
      '05-09 10:51 (KST 19:51)',
    );
  });

  test('respects explicit timestamp offsets when computing Korea time', () {
    expect(
      formatTimestampWithKst('2026-05-09T10:51:00Z'),
      '05-09 10:51 (KST 19:51)',
    );
    expect(
      formatTimestampWithKst('2026-05-09T10:51:00+09:00'),
      '05-09 10:51 (KST 10:51)',
    );
  });

  test('parses scheduler timestamps into KST for slot matching', () {
    expect(
      parseTimestampToKst('2026-09-08T00:34:38'),
      DateTime.utc(2026, 9, 8, 9, 34, 38),
    );
    expect(
      parseTimestampToKst('2026-09-08T03:03:25'),
      DateTime.utc(2026, 9, 8, 12, 3, 25),
    );
    expect(
      parseTimestampToKst('2026-09-08T04:33:47'),
      DateTime.utc(2026, 9, 8, 13, 33, 47),
    );
  });

  test('keeps fallback behavior for missing or unparseable values', () {
    expect(formatTimestampWithKst(''), '-');
    expect(formatTimestampWithKst(null), '-');
    expect(formatTimestampWithKst('not-a-time'), 'not-a-time');
  });
}
