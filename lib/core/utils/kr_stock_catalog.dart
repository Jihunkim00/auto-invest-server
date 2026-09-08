import 'dart:convert';

import 'package:flutter/services.dart';

import 'kr_symbol.dart';

const krStockCatalogAssetPath = 'assets/data/watchlist_kr_all.json';

/// Lookup-only KR stock catalog. It is deliberately separate from the active
/// automation watchlist and never mutates controller watchlist state.
class KrStockCatalog {
  KrStockCatalog({
    Future<String> Function(String assetPath)? loadString,
  }) : _loadString = loadString ?? rootBundle.loadString;

  static final shared = KrStockCatalog();

  final Future<String> Function(String assetPath) _loadString;
  List<KrStockLookupEntry>? _entries;
  Future<void>? _loadFuture;

  bool get isLoaded => _entries != null;

  List<KrStockLookupEntry> get entries =>
      _entries ?? const <KrStockLookupEntry>[];

  Future<void> load() {
    if (_entries != null) return Future<void>.value();
    return _loadFuture ??= _load();
  }

  KrStockMatch? resolve(String query) {
    return resolveKrStockEntries(query, entries);
  }

  String? displayName(String symbol) {
    final normalized = normalizeKrSymbol(symbol);
    if (normalized.isEmpty) return null;
    for (final entry in entries) {
      if (normalizeKrSymbol(entry.symbol) == normalized) {
        return entry.name;
      }
    }
    return null;
  }

  Future<void> _load() async {
    final raw = await _loadString(krStockCatalogAssetPath);
    final decoded = jsonDecode(raw);
    if (decoded is! Map) {
      throw const FormatException('KR stock catalog must be a JSON object.');
    }
    final rawSymbols = decoded['symbols'];
    if (rawSymbols is! List) {
      throw const FormatException('KR stock catalog symbols must be a list.');
    }

    final loaded = <KrStockLookupEntry>[];
    for (final rawEntry in rawSymbols.whereType<Map>()) {
      final symbol = normalizeKrSymbol(rawEntry['symbol']);
      if (!RegExp(r'^\d{6}$').hasMatch(symbol)) continue;
      final name = _stringValue(rawEntry['name']);
      if (name.isEmpty) continue;
      loaded.add(
        KrStockLookupEntry(
          symbol: symbol,
          name: name,
          englishName: _stringValue(rawEntry['english_name']),
          market: _stringValue(rawEntry['market']),
          aliases: _stringList(rawEntry['aliases']),
        ),
      );
    }
    if (loaded.isEmpty) {
      throw const FormatException('KR stock catalog contains no symbols.');
    }
    _entries = List<KrStockLookupEntry>.unmodifiable(loaded);
  }
}

String _stringValue(Object? value) {
  final text = value?.toString().trim() ?? '';
  return text == 'null' ? '' : text;
}

List<String> _stringList(Object? value) {
  if (value is! List) return const [];
  return value
      .map(_stringValue)
      .where((value) => value.isNotEmpty)
      .toList(growable: false);
}
