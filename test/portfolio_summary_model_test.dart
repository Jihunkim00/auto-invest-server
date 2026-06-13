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

  test('PositionSummary parses company-name aliases', () {
    final summary = PortfolioSummary.fromJson({
      'currency': 'USD',
      'positions': [
        {
          'symbol': 'AAPL',
          'company_name': 'Apple Inc.',
          'broker': 'alpaca',
          'market': 'US',
        },
        {
          'symbol': 'MSFT',
          'companyName': 'Microsoft Corporation',
        },
        {
          'symbol': 'NVDA',
          'asset_name': 'NVIDIA Corporation',
        },
      ],
      'pending_orders': const [],
    });

    expect(summary.positions[0].name, 'Apple Inc.');
    expect(summary.positions[0].broker, 'alpaca');
    expect(summary.positions[0].market, 'US');
    expect(summary.positions[1].name, 'Microsoft Corporation');
    expect(summary.positions[2].name, 'NVIDIA Corporation');
  });

  test('PositionSummary falls back to symbol instead of Unknown Company', () {
    final summary = PortfolioSummary.fromJson({
      'currency': 'USD',
      'positions': [
        {
          'symbol': 'AAPL',
          'company_name': 'Unknown Company',
        },
      ],
      'pending_orders': const [],
    });

    expect(summary.positions.single.name, 'AAPL');
  });
}
