import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

void main() {
  test('fetchKrPortfolioSummary maps balance cash to summary cash', () async {
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/kis/account/balance') {
          return http.Response(
              jsonEncode({'cash': 30000.0, 'stock_evaluation_amount': 0.0}),
              200);
        }
        if (request.url.path == '/kis/account/positions') {
          return http.Response(
              jsonEncode({'count': 0, 'positions': const []}), 200);
        }
        if (request.url.path == '/kis/account/open-orders') {
          return http.Response(
              jsonEncode({'count': 0, 'orders': const []}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    final summary = await client.fetchKrPortfolioSummary();

    expect(summary.currency, 'KRW');
    expect(summary.cash, 30000.0);
  });

  test('fetchKrPortfolioSummary falls back to dnca_tot_amt for cash', () async {
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/kis/account/balance') {
          return http.Response(
              jsonEncode(
                  {'dnca_tot_amt': '45000', 'stock_evaluation_amount': 0.0}),
              200);
        }
        if (request.url.path == '/kis/account/positions') {
          return http.Response(
              jsonEncode({'count': 0, 'positions': const []}), 200);
        }
        if (request.url.path == '/kis/account/open-orders') {
          return http.Response(
              jsonEncode({'count': 0, 'orders': const []}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    final summary = await client.fetchKrPortfolioSummary();

    expect(summary.cash, 45000.0);
  });

  test('fetchKrPortfolioSummary computes KR profit percent from cost basis',
      () async {
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/kis/account/balance') {
          return http.Response(
              jsonEncode({
                'purchase_amount': 9830,
                'stock_evaluation_amount': 9867,
                'unrealized_pl': 37,
                'unrealized_plpc': 0,
                'cash': 30000,
              }),
              200);
        }
        if (request.url.path == '/kis/account/positions') {
          return http.Response(
              jsonEncode({
                'count': 1,
                'positions': [
                  {
                    'symbol': '091810',
                    'qty': 11,
                    'avg_entry_price': 893.64,
                    'cost_basis': 9830,
                    'current_price': 897,
                    'market_value': 9867,
                    'unrealized_pl': 37,
                    'unrealized_plpc': 37,
                  }
                ],
              }),
              200);
        }
        if (request.url.path == '/kis/account/open-orders') {
          return http.Response(
              jsonEncode({'count': 0, 'orders': const []}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    final summary = await client.fetchKrPortfolioSummary();

    expect(summary.totalUnrealizedPlpc, closeTo(37 / 9830, 0.0000001));
    expect(summary.totalUnrealizedPlpc, isNot(37));
    expect(
        summary.positions.single.unrealizedPlpc, closeTo(37 / 9830, 0.0000001));
    expect(summary.positions.single.unrealizedPlpc, isNot(37));
  });

  test('fetchKrPortfolioSummary derives P/L percent from value minus cost',
      () async {
    final client = ApiClient(
      client: MockClient((request) async {
        if (request.url.path == '/kis/account/balance') {
          return http.Response(
              jsonEncode({
                'purchase_amount': 10000,
                'stock_evaluation_amount': 9800,
                'cash': 30000,
              }),
              200);
        }
        if (request.url.path == '/kis/account/positions') {
          return http.Response(
              jsonEncode({
                'count': 1,
                'positions': [
                  {
                    'symbol': '091810',
                    'qty': 10,
                    'avg_entry_price': 1000,
                    'cost_basis': 10000,
                    'current_price': 980,
                    'market_value': 9800,
                    'unrealized_plpc': -200,
                  }
                ],
              }),
              200);
        }
        if (request.url.path == '/kis/account/open-orders') {
          return http.Response(
              jsonEncode({'count': 0, 'orders': const []}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    final summary = await client.fetchKrPortfolioSummary();

    expect(summary.totalUnrealizedPlpc, closeTo(-200 / 10000, 0.0000001));
    expect(summary.positions.single.unrealizedPl, -200);
    expect(summary.positions.single.unrealizedPlpc, closeTo(-0.02, 0.0000001));
  });
}
