String normalizeKrSymbol(Object? value) {
  final raw = value?.toString().trim() ?? '';
  if (raw.isEmpty) return '';
  final digitsOnly = RegExp(r'^\d+$').hasMatch(raw);
  if (digitsOnly && raw.length < 6) {
    return raw.padLeft(6, '0');
  }
  return raw;
}
