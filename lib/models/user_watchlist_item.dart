class UserWatchlistItem {
  const UserWatchlistItem({
    this.id,
    required this.symbol,
    required this.provider,
    required this.market,
  });

  final int? id;
  final String symbol;
  final String provider;
  final String market;

  factory UserWatchlistItem.fromJson(Map<String, dynamic> json) {
    final rawId = json['id'];
    return UserWatchlistItem(
      id: rawId is num ? rawId.toInt() : int.tryParse(rawId?.toString() ?? ''),
      symbol: json['symbol']?.toString() ?? '',
      provider: json['provider']?.toString() ?? 'kis',
      market: json['market']?.toString() ?? 'KR',
    );
  }
}
