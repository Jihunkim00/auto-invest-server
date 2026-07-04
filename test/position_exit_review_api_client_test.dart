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
        if (request.url.path == '/strategy/positions/005930/guarded-sell') {
          return http.Response(
            jsonEncode(guardedSellResultJson(
              status: 'submitted',
              submitted: true,
            )),
            200,
          );
        }
        if (request.url.path == '/strategy/positions/sell-results/7/sync') {
          return http.Response(
            jsonEncode(guardedSellResultJson(
              status: 'filled',
              submitted: true,
            )),
            200,
          );
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
    final guardedSell = await client.runGuardedPositionSell(
      symbol: '005930',
      confirmLive: true,
      clientRequestId: 'guarded-ui-test',
      language: 'en',
      locale: 'en-US',
      reason: 'stop_loss_review',
    );
    final synced = await client.syncGuardedPositionSellResult(7);

    expect(review.positions.single.symbol, '005930');
    expect(preflight.isAllowed, isTrue);
    expect(guardedSell.realOrderSubmitted, isTrue);
    expect(synced.resultStatus, 'filled');
    expect(requests, hasLength(4));
    expect(requests.first.method, 'GET');
    expect(requests.first.url.path, '/strategy/positions/exit-review');
    expect(requests[1].method, 'POST');
    expect(requests[1].url.path, '/strategy/positions/005930/sell-preflight');

    final preflightBody = jsonDecode(requests[1].body) as Map<String, dynamic>;
    expect(preflightBody['provider'], 'kis');
    expect(preflightBody['market'], 'KR');
    expect(preflightBody['quantity_mode'], 'full');
    expect(preflightBody['language'], 'en');
    expect(preflightBody['locale'], 'en-US');
    expect(preflightBody.containsKey('confirm_live'), isFalse);
    expect(preflightBody.containsKey('confirm_operator_ack'), isFalse);
    expect(preflightBody.containsKey('submit_order'), isFalse);
    expect(preflightBody.containsKey('manual_submit'), isFalse);
    expect(preflightBody.containsKey('dry_run'), isFalse);
    expect(preflightBody.containsKey('kill_switch'), isFalse);

    expect(requests[2].method, 'POST');
    expect(requests[2].url.path, '/strategy/positions/005930/guarded-sell');
    final guardedBody = jsonDecode(requests[2].body) as Map<String, dynamic>;
    expect(guardedBody['confirm_live'], isTrue);
    expect(guardedBody['client_request_id'], 'guarded-ui-test');
    expect(guardedBody['reason'], 'stop_loss_review');
    expect(guardedBody.containsKey('confirm_operator_ack'), isFalse);

    expect(requests[3].method, 'POST');
    expect(requests[3].url.path, '/strategy/positions/sell-results/7/sync');
    final syncBody = jsonDecode(requests[3].body) as Map<String, dynamic>;
    expect(syncBody.containsKey('confirm_live'), isFalse);
    expect(syncBody.containsKey('manual_submit'), isFalse);
  });
}
