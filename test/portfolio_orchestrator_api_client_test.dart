import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';

import 'portfolio_orchestrator_model_test.dart';

void main() {
  test('latest status uses the read-only portfolio endpoint', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(portfolioOrchestratorJson()), 200);
      }),
    );

    final result = await api.fetchPortfolioOrchestratorLatest();

    expect(result.resultStatus, 'disabled');
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'GET');
    expect(request.url.path, '/automation/portfolio/latest');
    expect(request.url.queryParameters['provider'], 'kis');
    expect(request.url.queryParameters['market'], 'KR');
  });

  test('run once sends only the safe orchestrator payload', () async {
    final requests = <http.Request>[];
    final api = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(
          jsonEncode(
            portfolioOrchestratorJson(
              enabled: true,
              status: 'dry_run_completed',
            ),
          ),
          200,
        );
      }),
    );

    final result = await api.runPortfolioOrchestratorOnce(
      language: 'en',
      locale: 'en-US',
    );

    expect(result.resultStatus, 'dry_run_completed');
    expect(requests, hasLength(1));
    final request = requests.single;
    expect(request.method, 'POST');
    expect(request.url.path, '/automation/portfolio/run-once');
    final body = jsonDecode(request.body) as Map<String, dynamic>;
    expect(body, {
      'provider': 'kis',
      'market': 'KR',
      'trigger_source': 'manual_orchestrator_test',
      'mode': 'dry_run_monitoring',
      'language': 'en',
      'locale': 'en-US',
    });
    expect(body.keys, isNot(contains('confirm_live')));
    expect(body.keys, isNot(contains('force_run')));
    expect(body.keys, isNot(contains('skip_gates')));
    expect(body.keys, isNot(contains('disable_kill_switch')));
    expect(body.keys, isNot(contains('dry_run')));
  });
}
