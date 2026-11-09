class TradeFill {
  TradeFill.fromJson(Map<String, dynamic> json)
      : id = json['id'] as String,
        symbol = json['symbol'] as String,
        name = json['name'] as String? ?? '',
        side = json['side'] as String,
        quantity = ((json['filled_qty'] ?? json['quantity']) as num).toDouble(),
        averagePrice =
            ((json['avg_fill_price'] ?? json['average_price']) as num?)
                ?.toDouble(),
        amount =
            ((json['filled_amount'] ?? json['amount']) as num?)?.toDouble(),
        currency = json['currency'] as String,
        partial = json['partial'] == true,
        tradeDate = json['trade_date'] as String,
        filledAt = DateTime.tryParse(
            (json['executed_at'] ?? json['filled_at'])?.toString() ?? '') {
    if (!quantity.isFinite ||
        quantity <= 0 ||
        !['buy', 'sell'].contains(side)) {
      throw const FormatException('Invalid broker execution');
    }
  }

  final String id, symbol, name, side, currency, tradeDate;
  final double quantity;
  final double? averagePrice, amount;
  final bool partial;
  final DateTime? filledAt;
}

class TradeFillPage {
  TradeFillPage.fromJson(Map<String, dynamic> json)
      : items = (json['items'] as List)
            .map((item) => TradeFill.fromJson(Map<String, dynamic>.from(item)))
            .toList(),
        status = json['status'] as String? ?? 'success',
        code = json['code'] as String?,
        source = json['source'] as String? ?? 'persisted_broker_executions',
        count = ((json['count'] ?? json['summary']?['count']) as num?)?.toInt(),
        buyAmount = ((json['total_buy_amount'] ??
                json['summary']?['buy_amount']) as num?)
            ?.toDouble(),
        sellAmount = ((json['total_sell_amount'] ??
                json['summary']?['sell_amount']) as num?)
            ?.toDouble(),
        unknownAmountCount = ((json['unknown_amount_count'] ??
                    json['summary']?['unknown_amount_count']) as num?)
                ?.toInt() ??
            0,
        environment = json['environment'] as String?,
        endAt = json['end_at'] as String,
        nextOffset = (json['next_offset'] as num?)?.toInt() {
    if (status == 'success' &&
        (count == null ||
            count! < items.length ||
            (source == 'kis_broker_executions' && json['complete'] != true))) {
      throw const FormatException('Incomplete broker execution response');
    }
  }

  final List<TradeFill> items;
  final int? count;
  final int unknownAmountCount;
  final String status, source;
  final String? code;
  final double? buyAmount, sellAmount;
  final String? environment;
  final String endAt;
  final int? nextOffset;
}
