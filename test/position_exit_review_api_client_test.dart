import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'position_exit_review_model_test.dart';

void main() {
  test('position exit review API uses read-only endpoints', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        if (request.url.path == '/strategy/positions/exit-review') {
          return http.Response(jsonEncode(positionExitReviewJson()), 200);
        }
        return http.Response(
          jsonEncode(positionSellPreflightJson(status: 'allowed')),
          200,
        );
      }),
    );

    final review = await client.fetchPositionExitReview();
    final preflight = await client.runPositionSellPreflight(
      symbol: '005930',
      language: 'en',
      locale: 'en-US',
    );

    expect(review.positions.single.symbol, '005930');
    expect(preflight.isAllowed, isTrue);
    expect(requests, hasLength(2));
    expect(requests.first.method, 'GET');
    expect(requests.first.url.path, '/strategy/positions/exit-review');
    expect(requests.last.method, 'POST');
    expect(requests.last.url.path, '/strategy/positions/005930/sell-preflight');

    final body = jsonDecode(requests.last.body) as Map<String, dynamic>;
    expect(body['provider'], 'kis');
    expect(body['market'], 'KR');
    expect(body['quantity_mode'], 'full');
    expect(body['language'], 'en');
    expect(body['locale'], 'en-US');
    expect(body.containsKey('confirm_live'), isFalse);
    expect(body.containsKey('confirm_operator_ack'), isFalse);
    expect(body.containsKey('submit_order'), isFalse);
    expect(body.containsKey('manual_submit'), isFalse);
    expect(body.containsKey('dry_run'), isFalse);
    expect(body.containsKey('kill_switch'), isFalse);
  });
}
