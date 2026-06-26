import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'strategy_live_auto_buy_model_test.dart';

void main() {
  test('live auto buy API uses guarded endpoints and safe body', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        if (request.url.path.endsWith('/readiness')) {
          return http.Response(jsonEncode(liveReadinessJson(ready: true)), 200);
        }
        if (request.url.path.endsWith('/recent')) {
          return http.Response(
            jsonEncode({
              'provider': 'kis',
              'market': 'KR',
              'count': 1,
              'items': [
                liveRunResultJson(status: 'submitted', submitted: true)
              ],
              'safety': {'read_only': true},
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode(liveRunResultJson(status: 'submitted', submitted: true)),
          200,
        );
      }),
    );

    final readiness = await client.fetchStrategyLiveAutoBuyReadiness();
    final run = await client.runStrategyLiveAutoBuyOnce(
      symbol: '005930',
      promotionId: 7,
      sourceDryRunId: 20,
      clientRequestId: 'client-1',
    );
    final recent = await client.fetchStrategyLiveAutoBuyRecent();

    expect(readiness.ready, isTrue);
    expect(run.submitted, isTrue);
    expect(recent.items, hasLength(1));
    expect(requests[0].method, 'GET');
    expect(requests[0].url.path, '/strategy/live/auto-buy/readiness');
    expect(requests[1].method, 'POST');
    expect(requests[1].url.path, '/strategy/live/auto-buy/run-once');
    final body = jsonDecode(requests[1].body) as Map<String, dynamic>;
    expect(body['confirm_operator_ack'], isTrue);
    expect(body['promotion_id'], 7);
    expect(body['trigger_source'], 'flutter_dashboard');
    expect(body['client_request_id'], 'client-1');
    expect(body.containsKey('enable_scheduler'), isFalse);
    expect(body.containsKey('dry_run'), isFalse);
    expect(body.containsKey('kill_switch'), isFalse);
    expect(body.containsKey('kis_real_order_enabled'), isFalse);
    expect(requests[2].method, 'GET');
    expect(requests[2].url.path, '/strategy/live/auto-buy/recent');
  });
}
