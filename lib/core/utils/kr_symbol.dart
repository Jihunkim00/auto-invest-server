import '../../models/market_watchlist.dart';

String normalizeKrSymbol(Object? value) {
  final raw = value?.toString().trim() ?? '';
  if (raw.isEmpty) return '';
  final digitsOnly = RegExp(r'^\d+$').hasMatch(raw);
  if (digitsOnly && raw.length < 6) {
    return raw.padLeft(6, '0');
  }
  return raw;
}

/// A lookup-only Korean stock catalog entry.
class KrStockLookupEntry {
  const KrStockLookupEntry({
    required this.symbol,
    required this.name,
    this.englishName = '',
    this.market = '',
    this.aliases = const [],
  });

  final String symbol;
  final String name;
  final String englishName;
  final String market;
  final List<String> aliases;
}

/// A symbol/name match resolved entirely from client-side data.
class KrStockMatch {
  const KrStockMatch({required this.symbol, required this.name});

  final String symbol;
  final String name;
}

/// Resolves a stock from reusable lookup entries without touching automation
/// state.
KrStockMatch? resolveKrStockEntries(
  String text,
  Iterable<KrStockLookupEntry> sourceEntries,
) {
  final query = _normalizedStockText(text);
  if (query.isEmpty) return null;

  final entries = sourceEntries
      .map(_ResolvedStockEntry.fromCatalog)
      .where((entry) => entry.symbol.isNotEmpty)
      .toList();

  final symbolTokens = RegExp(r'(?<!\d)(\d{6})(?!\d)')
      .allMatches(text)
      .map((match) => match.group(1)!)
      .toSet()
      .toList();
  if (symbolTokens.isNotEmpty) {
    if (symbolTokens.length != 1) return null;
    final symbol = symbolTokens.single;
    final known = entries.where((entry) => entry.symbol == symbol).toList();
    if (known.length == 1) return known.single.toMatch();
    return KrStockMatch(symbol: symbol, name: _unknownName(symbol));
  }

  final exactName = _uniqueMatch(
    entries.where((entry) => entry.normalizedName == query).toList(),
  );
  if (exactName != null) return exactName;

  final exactEnglish = _uniqueMatch(
    entries.where((entry) => entry.normalizedEnglish == query).toList(),
  );
  if (exactEnglish != null) return exactEnglish;

  final exactAlias = _uniqueMatch(
    entries.where((entry) => entry.normalizedAliases.contains(query)).toList(),
  );
  if (exactAlias != null) return exactAlias;

  final contained = <_ResolvedStockEntry, int>{};
  for (final entry in entries) {
    final matchedLengths = entry.matchValues
        .where((value) => value.length >= 2 && query.contains(value))
        .map((value) => value.length);
    if (matchedLengths.isNotEmpty) {
      contained[entry] = matchedLengths.reduce(
        (longest, value) => value > longest ? value : longest,
      );
    }
  }
  if (contained.isNotEmpty) {
    final longest = contained.values.reduce(
      (current, value) => value > current ? value : current,
    );
    final longestMatches = contained.entries
        .where((entry) => entry.value == longest)
        .map((entry) => entry.key)
        .toList();
    final match = _uniqueMatch(longestMatches);
    if (match != null) return match;
  }

  final partial = entries
      .where(
        (entry) => entry.matchValues.any(
          (value) =>
              value.length >= 2 &&
              (value.contains(query) || query.contains(value)),
        ),
      )
      .toList();
  return _uniqueMatch(partial);
}

/// Resolves Korean stock names from the active watchlist.
///
/// This compatibility wrapper intentionally keeps the old caller contract.
/// New lookup flows should use [KrStockCatalog] and [resolveKrStockEntries].
KrStockMatch? resolveKrStockText(
  String text,
  MarketWatchlist watchlist,
) {
  return resolveKrStockEntries(
    text,
    watchlist.symbols.map(
      (item) => KrStockLookupEntry(
        symbol: item.symbol,
        name: item.name,
        englishName: item.companyName,
        market: item.market,
        aliases: item.aliases,
      ),
    ),
  );
}

String formatKrStockDisplay(
  String symbol, {
  String? name,
  MarketWatchlist? watchlist,
}) {
  final normalized = normalizeKrSymbol(symbol);
  final directName = name?.trim() ?? '';
  final resolved =
      watchlist == null ? null : resolveKrStockText(normalized, watchlist);
  final displayName = _displayName(
    directName.isNotEmpty ? directName : resolved?.name,
    normalized,
  );
  final code = normalized.isEmpty ? symbol.trim() : normalized;
  if (code.isEmpty) return displayName;
  return '$displayName ($code)';
}

String _normalizedStockText(String value) =>
    value.trim().toLowerCase().replaceAll(
          RegExp(r'[^\p{L}\p{N}]', unicode: true),
          '',
        );

KrStockMatch? _uniqueMatch(List<_ResolvedStockEntry> entries) {
  final uniqueBySymbol = <String, _ResolvedStockEntry>{
    for (final entry in entries) entry.symbol: entry,
  };
  if (uniqueBySymbol.length != 1) return null;
  return uniqueBySymbol.values.single.toMatch();
}

class _ResolvedStockEntry {
  const _ResolvedStockEntry({
    required this.symbol,
    required this.name,
    required this.normalizedName,
    required this.normalizedEnglish,
    required this.normalizedAliases,
    required this.matchValues,
  });

  final String symbol;
  final String name;
  final String normalizedName;
  final String normalizedEnglish;
  final Set<String> normalizedAliases;
  final Set<String> matchValues;

  factory _ResolvedStockEntry.fromCatalog(KrStockLookupEntry item) {
    final symbol = normalizeKrSymbol(item.symbol);
    final name = _displayName(item.name, symbol);
    final normalizedName = _normalizedStockText(name);
    final normalizedEnglish = _normalizedStockText(item.englishName);
    final normalizedAliases = <String>{
      for (final alias in item.aliases)
        if (_normalizedStockText(alias).isNotEmpty) _normalizedStockText(alias),
    };
    final matchValues = <String>{
      if (normalizedName.isNotEmpty) normalizedName,
      if (normalizedEnglish.isNotEmpty) normalizedEnglish,
      ...normalizedAliases,
    };
    for (final value in [...matchValues]) {
      final suffix = value.replaceFirst(RegExp(r'^[a-z0-9]+'), '');
      if (suffix.length >= 2) matchValues.add(suffix);
    }
    return _ResolvedStockEntry(
      symbol: symbol,
      name: name,
      normalizedName: normalizedName,
      normalizedEnglish: normalizedEnglish,
      normalizedAliases: normalizedAliases,
      matchValues: matchValues,
    );
  }

  KrStockMatch toMatch() => KrStockMatch(symbol: symbol, name: name);
}

String _displayName(Object? value, String symbol) {
  final text = value?.toString().trim() ?? '';
  if (text.isEmpty || text.toUpperCase() == symbol.toUpperCase()) {
    return _unknownName(symbol);
  }
  return text;
}

String _unknownName(String symbol) => '종목명 미확인';
