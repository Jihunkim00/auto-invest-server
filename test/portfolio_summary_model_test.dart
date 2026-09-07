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

  test('PortfolioSummary.fromJson parses nullable KIS asset fields', () {
    final summary = PortfolioSummary.fromJson({
      'currency': 'KRW',
      'cash': 103455,
      'cash_balance': 103455,
      'withdrawable_cash': null,
      'd1_cash': 306130,
      'd2_cash': null,
      'orderable_cash': null,
      'orderable_cash_status': 'candidate_required',
      'orderable_cash_source': null,
      'total_asset_value': 306130,
      'stock_evaluation_amount': 0,
      'positions': const [],
      'pending_orders': const [],
    });

    expect(summary.totalAssetValue, 306130);
    expect(summary.stockEvaluationAmount, 0);
    expect(summary.cashBalance, 103455);
    expect(summary.withdrawableCash, isNull);
    expect(summary.orderableCash, isNull);
    expect(summary.orderableCashStatus, 'candidate_required');
    expect(summary.orderableCashSource, isNull);
    expect(summary.d1Cash, 306130);
    expect(summary.d2Cash, isNull);
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
