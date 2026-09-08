import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

void main() {
  test('fetchKisMarketPrice calls the existing read-only endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode({
            'provider': 'kis',
            'symbol': '000660',
            'name': 'SK\\uD558\\uC774\\uB2C9\\uC2A4',
            'current_price': 123456,
            'currency': 'KRW',
          }),
          200,
        );
      }),
    );

    final result = await api.fetchKisMarketPrice('000660');

    expect(requests.single.method, 'GET');
    expect(requests.single.url.path, '/kis/market/price/000660');
    expect(requests.single.url.queryParameters.containsKey('_ts'), isTrue);
    expect(result['symbol'], '000660');
    expect(result['current_price'], 123456);
  });
}
