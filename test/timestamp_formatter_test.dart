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

  test('keeps fallback behavior for missing or unparseable values', () {
    expect(formatTimestampWithKst(''), '-');
    expect(formatTimestampWithKst(null), '-');
    expect(formatTimestampWithKst('not-a-time'), 'not-a-time');
  });
}
