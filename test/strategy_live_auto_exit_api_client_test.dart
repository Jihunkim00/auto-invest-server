import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'strategy_live_auto_exit_model_test.dart';

void main() {
  test('live auto exit API uses guarded endpoints and safe body', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        if (request.url.path.endsWith('/readiness')) {
          return http.Response(
            jsonEncode(liveExitReadinessJson(ready: true)),
            200,
          );
        }
        if (request.url.path.endsWith('/recent')) {
          return http.Response(
            jsonEncode({
              'provider': 'kis',
              'market': 'KR',
              'count': 1,
              'items': [
                liveExitRunResultJson(status: 'submitted', submitted: true)
              ],
              'safety': {'read_only': true},
            }),
            200,
          );
        }
        return http.Response(
          jsonEncode(liveExitRunResultJson(
            status: 'submitted',
            submitted: true,
          )),
          200,
        );
      }),
    );

    final readiness = await client.fetchStrategyLiveAutoExitReadiness();
    final run = await client.runStrategyLiveAutoExitOnce(
      symbol: '005930',
      clientRequestId: 'client-exit-1',
    );
    final recent = await client.fetchStrategyLiveAutoExitRecent();

    expect(readiness.ready, isTrue);
    expect(run.submitted, isTrue);
    expect(recent.items, hasLength(1));
    expect(requests[0].method, 'GET');
    expect(requests[0].url.path, '/strategy/live/auto-exit/readiness');
    expect(requests[1].method, 'POST');
    expect(requests[1].url.path, '/strategy/live/auto-exit/run-once');
    final body = jsonDecode(requests[1].body) as Map<String, dynamic>;
    expect(body['confirm_operator_ack'], isTrue);
    expect(body['trigger_source'], 'flutter_dashboard');
    expect(body['client_request_id'], 'client-exit-1');
    expect(body.containsKey('enable_scheduler'), isFalse);
    expect(body.containsKey('dry_run'), isFalse);
    expect(body.containsKey('kill_switch'), isFalse);
    expect(body.containsKey('kis_real_order_enabled'), isFalse);
    expect(requests[2].method, 'GET');
    expect(requests[2].url.path, '/strategy/live/auto-exit/recent');
  });
}
