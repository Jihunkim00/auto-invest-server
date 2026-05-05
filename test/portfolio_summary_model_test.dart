import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

void main() {
  test('PortfolioSummary.fromJson parses cash', () {
    final summary = PortfolioSummary.fromJson({
      'currency': 'KRW',
      'cash': 30000,
      'positions': const [],
      'pending_orders': const [],
    });

    expect(summary.cash, 30000);
  });

  test('PortfolioSummary.fromJson defaults cash to 0 when missing', () {
    final summary = PortfolioSummary.fromJson({
      'currency': 'USD',
      'positions': const [],
      'pending_orders': const [],
    });

    expect(summary.cash, 0);
  });
}
