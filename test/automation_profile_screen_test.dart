import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
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
    tester.view.physicalSize = const Size(800, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final client = _ProfileClient();
    await tester.pumpWidget(MaterialApp(
      supportedLocales: const [Locale('ko', 'KR'), Locale('en', 'US')],
      home: AutomationProfileScreen(apiClient: ApiClient(client: client)),
    ));
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

  testWidgets('date fields open a calendar and keep API date serialization',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final client = _ProfileClient();
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      supportedLocales: const [Locale('ko', 'KR'), Locale('en', 'US')],
      home: AutomationProfileScreen(apiClient: ApiClient(client: client)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('automation-profile-1')));
    await tester.pump();

    final startField = tester.widget<TextField>(
      find.byKey(const ValueKey('automation-profile-start-date')),
    );
    expect(startField.readOnly, isTrue);
    expect(find.byIcon(Icons.calendar_month_outlined), findsNWidgets(2));

    await tester.tap(
      find.byKey(const ValueKey('automation-profile-start-date')),
    );
    await tester.pumpAndSettle();
    expect(find.byType(CalendarDatePicker), findsOneWidget);
    expect(find.text('시작일 선택'), findsOneWidget);

    await tester.tap(find.text('취소'));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('automation-profile-save')));
    await tester.pumpAndSettle();

    final operation = client.writes.last['operation'] as Map;
    expect(operation['start_date'], '2026-08-17');
    expect(operation['end_date'], '2026-09-18');
  });

  testWidgets(
      'save payload preserves selected sizing mode and unrelated capital settings',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1800);
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
    final operation = client.writes.last['operation'] as Map;
    expect(operation['start_date'], '2026-08-17');
    expect(operation['end_date'], '2026-09-18');
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

  testWidgets('profile fields use external labels and comfortable controls',
      (tester) async {
    tester.view.physicalSize = const Size(800, 1600);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final client = _ProfileClient();
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      supportedLocales: const [Locale('ko', 'KR'), Locale('en', 'US')],
      home: AutomationProfileScreen(apiClient: ApiClient(client: client)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('automation-profile-1')));
    await tester.pump();

    for (final key in [
      'automation-profile-name',
      'automation-profile-start-date',
      'automation-profile-end-date',
      'automation-profile-target-pct',
      'automation-profile-max-order',
      'automation-profile-fixed-budget',
      'automation-profile-take-profit',
    ]) {
      final field = tester.widget<TextField>(find.byKey(ValueKey(key)));
      expect(field.decoration?.labelText, isNull, reason: key);
      expect(tester.getSize(find.byKey(ValueKey(key))).height,
          greaterThanOrEqualTo(48),
          reason: key);
    }
    expect(find.text('프로필 이름'), findsOneWidget);
    expect(find.text('시작일'), findsOneWidget);
    expect(find.text('종료일'), findsOneWidget);
    expect(find.text('관심종목 수'), findsOneWidget);
    expect(find.text('최대 보유 종목'), findsOneWidget);
    expect(find.text('목표 포지션 비율'), findsOneWidget);
    expect(find.byType(InputChip), findsOneWidget);
    expect(find.byIcon(Icons.calendar_month_outlined), findsNWidgets(2));
  });

  testWidgets('profile controls stack at phone width with larger text',
      (tester) async {
    tester.view.physicalSize = const Size(430, 2200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final client = _ProfileClient();
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: GlobalMaterialLocalizations.delegates,
      supportedLocales: const [Locale('ko', 'KR'), Locale('en', 'US')],
      builder: (context, child) => MediaQuery(
        data:
            MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(1.3)),
        child: child!,
      ),
      home: AutomationProfileScreen(apiClient: ApiClient(client: client)),
    ));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('automation-profile-1')));
    await tester.pumpAndSettle();

    final start = find.byKey(const ValueKey('automation-profile-start-date'));
    final end = find.byKey(const ValueKey('automation-profile-end-date'));
    expect(tester.getTopLeft(start).dy, lessThan(tester.getTopLeft(end).dy));
    expect(tester.takeException(), isNull);
  });
}
