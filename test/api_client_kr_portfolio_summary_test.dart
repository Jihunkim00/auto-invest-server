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
          return http.Response(jsonEncode({'count': 0, 'positions': const []}), 200);
        }
        if (request.url.path == '/kis/account/open-orders') {
          return http.Response(jsonEncode({'count': 0, 'orders': const []}), 200);
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
              jsonEncode({'dnca_tot_amt': '45000', 'stock_evaluation_amount': 0.0}),
              200);
        }
        if (request.url.path == '/kis/account/positions') {
          return http.Response(jsonEncode({'count': 0, 'positions': const []}), 200);
        }
        if (request.url.path == '/kis/account/open-orders') {
          return http.Response(jsonEncode({'count': 0, 'orders': const []}), 200);
        }
        return http.Response('not found', 404);
      }),
    );

    final summary = await client.fetchKrPortfolioSummary();

    expect(summary.cash, 45000.0);
  });
}
