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
  });

  factory WatchlistSymbol.fromJson(Map<String, dynamic> json) {
    return WatchlistSymbol(
      symbol: _readString(json['symbol'], ''),
      name: _readString(json['name'], ''),
      market: _readString(json['market'], ''),
    );
  }

  final String symbol;
  final String name;
  final String market;
}

int _readInt(Object? value, int fallback) {
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '') ?? fallback;
}

String _readString(Object? value, String fallback) {
  final text = value?.toString();
  if (text == null || text.isEmpty) return fallback;
  return text;
}
