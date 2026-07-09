import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'auto_sell_live_phase1_model_test.dart';

void main() {
  test('fetch sell phase one status calls read-only status endpoint', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(autoSellLivePhase1Json()), 200);
      }),
    );

    final result = await client.fetchAutoSellLivePhase1Status();

    expect(result.resultStatus, 'disabled');
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(
      request.url.path,
      '/strategy/positions/auto-sell/live-phase1/status',
    );
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
    expect(request.url.queryParameters, isNot(contains('confirm_live')));
    expect(request.url.path, isNot(contains('/guarded-sell')));
    expect(request.url.path, isNot(contains('/submit')));
  });

  test('run sell phase one once sends phase confirmation without confirm_live',
      () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode(autoSellLivePhase1Json(
            enabled: true,
            status: 'submitted',
            realOrderSubmitted: true,
            brokerSubmitCalled: true,
            selectedCandidateId: 'exit-005930-stop',
            selectedSymbol: '005930',
            orderId: 55,
            brokerOrderId: 'KIS-SELL-1',
            dailyCount: 1,
          )),
          200,
        );
      }),
    );

    final result = await client.runAutoSellLivePhase1Once(
      symbol: '005930',
      candidateId: 'exit-005930-stop',
      language: 'ko',
      locale: 'ko-KR',
    );

    expect(result.submitted, isTrue);
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'POST');
    expect(
      request.url.path,
      '/strategy/positions/auto-sell/live-phase1/run-once',
    );
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body['provider'], 'kis');
    expect(body['market'], 'KR');
    expect(body['symbol'], '005930');
    expect(body['candidate_id'], 'exit-005930-stop');
    expect(body['trigger_source'], 'manual_phase1_test');
    expect(body['confirm_phase1_run'], isTrue);
    expect(body, isNot(contains('confirm_live')));
    expect(body, isNot(contains('dry_run')));
    expect(body, isNot(contains('disable_kill')));
    expect(body, isNot(contains('liquidate')));
    expect(request.url.path, isNot(contains('/guarded-sell')));
  });
}
