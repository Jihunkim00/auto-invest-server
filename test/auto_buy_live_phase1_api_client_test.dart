import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'auto_buy_live_phase1_model_test.dart';

void main() {
  test('fetch phase one status calls read-only status endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(autoBuyLivePhase1Json()), 200);
      }),
    );

    final result = await client.fetchAutoBuyLivePhase1Status();

    expect(result.resultStatus, 'disabled');
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/strategy/auto-buy/live-phase1/status');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters, isNot(contains('confirm_live')));
    expect(request.url.path, isNot(contains('/guarded-buy')));
    expect(request.url.path, isNot(contains('/submit')));
  });

  test('run phase one once sends phase confirmation without confirm_live',
      () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode(autoBuyLivePhase1Json(
            enabled: true,
            status: 'submitted',
            realOrderSubmitted: true,
            brokerSubmitCalled: true,
            selectedPromotionId: 7,
            selectedSymbol: '005930',
            orderId: 55,
            brokerOrderId: 'KIS-ORDER-1',
            dailyCount: 1,
          )),
          200,
        );
      }),
    );

    final result = await client.runAutoBuyLivePhase1Once(
      promotionId: 7,
      language: 'ko',
      locale: 'ko-KR',
    );

    expect(result.submitted, isTrue);
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.path, '/strategy/auto-buy/live-phase1/run-once');
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body['provider'], 'kis');
    expect(body['market'], 'KR');
    expect(body['promotion_id'], 7);
    expect(body['trigger_source'], 'manual_phase1_test');
    expect(body['confirm_phase1_run'], isTrue);
    expect(body, isNot(contains('confirm_live')));
    expect(body, isNot(contains('dry_run')));
    expect(body, isNot(contains('disable_kill')));
    expect(request.url.path, isNot(contains('/guarded-buy')));
  });
}
