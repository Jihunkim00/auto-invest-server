import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/automation_profile/automation_profile_screen.dart';

class _ProfileClient extends http.BaseClient {
  final Map<String, dynamic> profile = {
    'id': 1,
    'profile_key': 'demo',
    'name': 'Demo profile',
    'provider': 'kis',
    'market': 'KR',
    'enabled': false,
    'status': 'disabled',
    'settings': {
      'max_open_positions': 1,
      'capital': {'sizing_mode': 'equity_pct', 'target_position_pct': 10, 'max_order_notional_krw': 500000},
      'universe': {'watchlist_size': 50},
      'entry': {'analysis_times': ['09:10']},
      'operation': {'start_date': '2026-08-17', 'end_date': '2026-09-18'},
      'exit': {'stop_loss_pct': 2, 'take_profit_pct': 3},
    },
  };

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    dynamic body;
    if (request.url.path == '/strategy-profiles') {
      body = request.method == 'GET' ? {'profiles': [profile], 'active_profile': null} : profile;
    } else if (request.url.path == '/symbols/search') {
      body = {'results': [{'symbol': '005930', 'name': '삼성전자'}]};
    } else {
      body = profile;
    }
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(Stream.value(bytes), 200, headers: {'content-type': 'application/json'});
  }
}

void main() {
  testWidgets('profile list and editor show PR109 warning without live start', (tester) async {
    await tester.pumpWidget(MaterialApp(home: AutomationProfileScreen(apiClient: ApiClient(client: _ProfileClient()))));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('automation-profile-1')), findsOneWidget);
    expect(find.byKey(const ValueKey('automation-profile-save')), findsOneWidget);
    expect(find.text('Start Live Auto'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('automation-profile-max-positions')));
    await tester.enterText(find.byKey(const ValueKey('automation-profile-max-positions')), '2');
    await tester.pump();
    expect(find.byKey(const ValueKey('automation-profile-multi-position-warning')), findsOneWidget);
  });
}
