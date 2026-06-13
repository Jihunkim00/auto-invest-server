class MarketWatchlist {
  const MarketWatchlist({
    required this.market,
    required this.currency,
    required this.timezone,
    required this.watchlistFile,
    required this.count,
    required this.symbols,
  });

  factory MarketWatchlist.empty(String market) => MarketWatchlist(
        market: market,
        currency: market == 'KR' ? 'KRW' : 'USD',
        timezone: market == 'KR' ? 'Asia/Seoul' : 'America/New_York',
        watchlistFile: '',
        count: 0,
        symbols: const [],
      );

  factory MarketWatchlist.fromJson(Map<String, dynamic> json) {
    final rawSymbols = json['symbols'] as List<dynamic>? ?? const [];
    return MarketWatchlist(
      market: _readString(json['market'], ''),
      currency: _readString(json['currency'], ''),
      timezone: _readString(json['timezone'], ''),
      watchlistFile: _readString(json['watchlist_file'], ''),
      count: _readInt(json['count'], rawSymbols.length),
      symbols: rawSymbols
          .whereType<Map>()
          .map((item) => WatchlistSymbol.fromJson(
              Map<String, dynamic>.from(item.cast<String, dynamic>())))
          .toList(),
    );
  }

  final String market;
  final String currency;
  final String timezone;
  final String watchlistFile;
  final int count;
  final List<WatchlistSymbol> symbols;
}

class WatchlistSymbol {
  const WatchlistSymbol({
    required this.symbol,
    required this.name,
    required this.market,
    this.companyName = '',
    this.marketLabel = '',
  });

  factory WatchlistSymbol.fromJson(Map<String, dynamic> json) {
    final symbol = _readString(json['symbol'] ?? json['ticker'], '');
    final companyName = _firstString([
      json['company_name'],
      json['companyName'],
      json['name'],
      json['company'],
      json['display_name'],
      json['asset_name'],
      symbol,
      'Unknown Company',
    ], symbol: symbol);
    return WatchlistSymbol(
      symbol: symbol,
      name: companyName,
      market: _readString(json['market'], ''),
      companyName: companyName,
      marketLabel: _readString(json['market_label'], ''),
    );
  }

  final String symbol;
  final String name;
  final String market;
  final String companyName;
  final String marketLabel;
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

String _readString(Object? value, String fallback) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return fallback;
  return text;
}

String _firstString(List<Object?> values, {String symbol = ''}) {
  String fallback = '';
  for (final value in values) {
    final text = _readString(value, '');
    if (text.toLowerCase() == 'unknown company' && symbol.isNotEmpty) {
      continue;
    }
    if (symbol.isNotEmpty && text.toUpperCase() == symbol.toUpperCase()) {
      fallback = text;
      continue;
    }
    if (text.isNotEmpty) return text;
  }
  return fallback;
}
