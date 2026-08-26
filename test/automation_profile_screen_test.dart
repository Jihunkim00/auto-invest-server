import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/automation_profile/automation_profile_screen.dart';

class _ProfileClient extends http.BaseClient {
  final List<Map<String, dynamic>> writes = <Map<String, dynamic>>[];
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
      'capital': {
        'sizing_mode': 'fixed_budget',
        'target_position_pct': 10,
        'max_position_pct': 12,
        'max_total_exposure_pct': 30,
        'fixed_budget': 500000,
        'max_order_notional_krw': 500000,
      },
      'universe': {'watchlist_size': 50},
      'entry': {
        'analysis_times': ['09:10']
      },
      'operation': {'start_date': '2026-08-17', 'end_date': '2026-09-18'},
      'exit': {'stop_loss_pct': 2, 'take_profit_pct': 3},
    },
  };

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    if (request is http.Request &&
        request.method != 'GET' &&
        request.body.isNotEmpty) {
      writes.add(Map<String, dynamic>.from(jsonDecode(request.body) as Map));
    }
    dynamic body;
    if (request.url.path == '/strategy-profiles') {
      body = request.method == 'GET'
          ? {
              'profiles': [profile],
              'active_profile': null
            }
          : profile;
    } else if (request.url.path == '/symbols/search') {
      body = {
        'results': [
          {'symbol': '005930', 'name': '삼성전자'}
        ]
      };
    } else {
      body = profile;
    }
    final bytes = utf8.encode(jsonEncode(body));
    return http.StreamedResponse(Stream.value(bytes), 200,
        headers: {'content-type': 'application/json'});
  }
}

void main() {
  testWidgets('fixed budget profile loads with mode-aware controls',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final client = _ProfileClient();
    await tester.pumpWidget(MaterialApp(
        home: AutomationProfileScreen(apiClient: ApiClient(client: client))));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('automation-profile-1')), findsOneWidget);
    expect(
        find.byKey(const ValueKey('automation-profile-save')), findsOneWidget);
    expect(find.text('Start Live Auto'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('automation-profile-1')));
    await tester.pump();
    final target = tester.widget<TextField>(
      find.byKey(const ValueKey('automation-profile-target-pct')),
    );
    final fixed = tester.widget<TextField>(
      find.byKey(const ValueKey('automation-profile-fixed-budget')),
    );
    expect(target.enabled, isFalse);
    expect(fixed.enabled, isTrue);
    expect(find.byKey(const ValueKey('automation-profile-target-pct-helper')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('automation-profile-fixed-budget-helper')),
        findsNothing);

    await tester.tap(find
        .byKey(const ValueKey('automation-profile-sizing-mode-fixed_budget')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('automation-profile-sizing-equity-pct')),
      warnIfMissed: false,
    );
    await tester.pump();
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('automation-profile-target-pct')))
            .enabled,
        isTrue);
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('automation-profile-fixed-budget')))
            .enabled,
        isFalse);
    expect(find.byKey(const ValueKey('automation-profile-fixed-budget-helper')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('automation-profile-target-pct-helper')),
        findsNothing);

    await tester
        .tap(find.byKey(const ValueKey('automation-profile-max-positions')));
    await tester.enterText(
        find.byKey(const ValueKey('automation-profile-max-positions')), '2');
    await tester.pump();
    expect(
        find.byKey(const ValueKey('automation-profile-multi-position-warning')),
        findsOneWidget);
  });

  testWidgets(
      'save payload preserves selected sizing mode and unrelated capital settings',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final client = _ProfileClient();
    await tester.pumpWidget(MaterialApp(
        home: AutomationProfileScreen(apiClient: ApiClient(client: client))));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('automation-profile-1')));
    await tester.pump();
    await tester.enterText(
        find.byKey(const ValueKey('automation-profile-fixed-budget')),
        '600000');
    await tester.tap(find.byKey(const ValueKey('automation-profile-save')));
    await tester.pumpAndSettle();
    expect(client.writes, isNotEmpty);
    final fixedCapital = client.writes.last['capital'] as Map;
    expect(fixedCapital['sizing_mode'], 'fixed_budget');
    expect(fixedCapital['fixed_budget'], 600000);
    expect(fixedCapital['max_position_pct'], 12);
    expect(fixedCapital['max_total_exposure_pct'], 30);

    await tester.drag(find.byType(ListView), const Offset(0, 600));
    await tester.pump();
    await tester.tap(find
        .byKey(const ValueKey('automation-profile-sizing-mode-fixed_budget')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('automation-profile-sizing-equity-pct')),
      warnIfMissed: false,
    );
    await tester.pump();
    await tester.enterText(
        find.byKey(const ValueKey('automation-profile-target-pct')), '12');
    await tester.scrollUntilVisible(
      find.byKey(const ValueKey('automation-profile-save')),
      300,
      scrollable: find.byType(Scrollable).first,
    );
    await tester.tap(find.byKey(const ValueKey('automation-profile-save')));
    await tester.pumpAndSettle();
    final equityCapital = client.writes.last['capital'] as Map;
    expect(equityCapital['sizing_mode'], 'equity_pct');
    expect(equityCapital['target_position_pct'], 12);
    expect(equityCapital['fixed_budget'], 600000);
  });
}
