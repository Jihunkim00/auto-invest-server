import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Dart sources are valid UTF-8 and do not contain mojibake markers', () {
    final failures = <String>[];

    for (final file in _dartSourceFiles()) {
      late final String text;
      try {
        text = utf8.decode(file.readAsBytesSync(), allowMalformed: false);
      } on FormatException catch (error) {
        failures.add('${file.path}: invalid UTF-8: $error');
        continue;
      }

      for (final marker in _forbiddenMarkers) {
        final index = text.indexOf(marker);
        if (index < 0) continue;
        final line = 1 + '\n'.allMatches(text.substring(0, index)).length;
        final codePoint = marker.runes.single.toRadixString(16).toUpperCase();
        failures.add('${file.path}:$line contains mojibake marker U+$codePoint');
      }
    }

    expect(failures, isEmpty, reason: failures.join('\n'));
  });
}

Iterable<File> _dartSourceFiles() sync* {
  for (final root in const ['lib', 'test']) {
    final directory = Directory(root);
    if (!directory.existsSync()) continue;
    for (final entity in directory.listSync(recursive: true)) {
      if (entity is File && entity.path.endsWith('.dart')) {
        yield entity;
      }
    }
  }
}

final _forbiddenMarkers = List<String>.unmodifiable(
  const <int>[
    0xFFFD,
    0x5360,
    0x7B4C,
    0x7670,
    0x96C5,
    0x63F6,
    0x8881,
    0x9913,
    0x91C9,
    0xF9CD,
    0xF9E4,
    0x5AC4,
    0x8E42,
    0x91AB,
  ].map(String.fromCharCode),
);
