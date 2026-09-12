import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/automation_profile/automation_profile_screen.dart';
import 'package:auto_invest_dashboard/models/automation_strategy_profile.dart';

void main() {
  testWidgets('Admin and regular users share the full profile editor',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() async => tester.binding.setSurfaceSize(null));

    final adminApi = _ScopedProfileApi();
    await tester.pumpWidget(
      MaterialApp(
        home: AutomationProfileScreen(
          key: const ValueKey('admin-profile-screen'),
          apiClient: adminApi,
        ),
      ),
    );
    await tester.pumpAndSettle();

    _expectFullEditor(tester);
    expect(adminApi.adminFetchCount, 1);
    expect(adminApi.userFetchCount, 0);
    expect(
        find.byKey(const ValueKey('user-auto-trading-enabled')), findsNothing);

    final userApi = _ScopedProfileApi();
    var refreshCount = 0;
    await tester.pumpWidget(
      MaterialApp(
        home: AutomationProfileScreen(
          key: const ValueKey('user-profile-screen'),
          apiClient: userApi,
          userScoped: true,
          onUserSettingsSaved: () async => refreshCount += 1,
        ),
      ),
    );
    await tester.pumpAndSettle();

    _expectFullEditor(tester);
    expect(userApi.userFetchCount, 1);
    expect(userApi.adminFetchCount, 0);
    expect(
        find.byKey(const ValueKey('user-auto-trading-enabled')), findsNothing);
    expect(find.byKey(const ValueKey('automation-profile-trading-mode')),
        findsNothing);

    await tester.enterText(
      find.byKey(const ValueKey('automation-profile-name')),
      'User profile',
    );
    await _scrollTo(tester, 'automation-profile-save');
    await tester.tap(find.byKey(const ValueKey('automation-profile-save')));
    await tester.pumpAndSettle();

    expect(userApi.userCreateCount, 1);
    expect(userApi.adminCreateCount, 0);
    expect(refreshCount, 1);
  });

  testWidgets('regular profile actions use only the user-owned API',
      (tester) async {
    final api = _ScopedProfileApi();

    await tester.pumpWidget(
      MaterialApp(
        home: AutomationProfileScreen(
          apiClient: api,
          userScoped: true,
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('automation-profile-1')));
    await tester.pumpAndSettle();
    await _scrollTo(tester, 'automation-profile-validate');
    await tester.tap(find.byKey(const ValueKey('automation-profile-validate')));
    await tester.pumpAndSettle();
    await _scrollTo(tester, 'automation-profile-start');
    await tester.tap(find.byKey(const ValueKey('automation-profile-start')));
    await tester.pumpAndSettle();

    expect(api.userValidateCount, 1);
    expect(api.userActivateCount, 1);
    expect(api.adminValidateCount, 0);
    expect(api.adminActivateCount, 0);
  });
}

Future<void> _scrollTo(WidgetTester tester, String key) {
  return _dragToProfileAction(tester, key);
}

Future<void> _dragToProfileAction(WidgetTester tester, String key) async {
  final target = find.byKey(ValueKey(key));
  final scrollable =
      find.byKey(const ValueKey('automation-profile-scroll-view'));
  for (var i = 0; i < 8; i += 1) {
    final rect = tester.getRect(target);
    final viewport = tester.getRect(scrollable);
    if (rect.top >= viewport.top && rect.bottom <= viewport.bottom) return;
    await tester.drag(scrollable, const Offset(0, -600));
    await tester.pumpAndSettle();
  }
}

void _expectFullEditor(WidgetTester tester) {
  const keys = [
    'automation-profile-editor',
    'automation-profile-name',
    'automation-profile-start-date',
    'automation-profile-end-date',
    'automation-profile-max-daily-trades',
    'automation-profile-add-analysis-time',
    'automation-profile-watchlist-size',
    'automation-profile-max-positions',
    'automation-profile-sizing-equity-pct',
    'automation-profile-target-pct',
    'automation-profile-max-position-pct',
    'automation-profile-max-exposure-pct',
    'automation-profile-fixed-budget',
    'automation-profile-compound-enabled',
    'automation-profile-stop-loss',
    'automation-profile-take-profit',
    'automation-profile-save',
    'automation-profile-validate',
    'automation-profile-search',
  ];
  for (final key in keys) {
    expect(find.byKey(ValueKey(key)), findsOneWidget, reason: key);
  }
}

class _ScopedProfileApi extends ApiClient {
  int adminFetchCount = 0;
  int userFetchCount = 0;
  int adminCreateCount = 0;
  int userCreateCount = 0;
  int adminValidateCount = 0;
  int userValidateCount = 0;
  int adminActivateCount = 0;
  int userActivateCount = 0;

  AutomationStrategyProfileList _profiles() {
    return AutomationStrategyProfileList.fromJson({
      'profiles': [_profileJson()],
      'selected_profile': null,
      'selected_profile_status': null,
      'active_profile': null,
    });
  }

  @override
  Future<AutomationStrategyProfileList> fetchAutomationProfiles() async {
    adminFetchCount += 1;
    return _profiles();
  }

  @override
  Future<AutomationStrategyProfileList> fetchUserAutomationProfiles() async {
    userFetchCount += 1;
    return _profiles();
  }

  @override
  Future<AutomationStrategyProfile> createAutomationProfile(
      Map<String, dynamic> body) async {
    adminCreateCount += 1;
    return AutomationStrategyProfile.fromJson(
      _profileJson(name: body['name']?.toString() ?? 'Admin profile'),
    );
  }

  @override
  Future<AutomationStrategyProfile> createUserAutomationProfile(
      Map<String, dynamic> body) async {
    userCreateCount += 1;
    return AutomationStrategyProfile.fromJson(
      _profileJson(name: body['name']?.toString() ?? 'User profile'),
    );
  }

  @override
  Future<Map<String, dynamic>> validateAutomationProfile(int profileId) async {
    adminValidateCount += 1;
    return {'valid': true, 'errors': <dynamic>[]};
  }

  @override
  Future<Map<String, dynamic>> validateUserAutomationProfile(
      int profileId) async {
    userValidateCount += 1;
    return {'valid': true, 'errors': <dynamic>[]};
  }

  @override
  Future<Map<String, dynamic>> activateAutomationProfile(int profileId,
      {bool confirmOperatorAck = true}) async {
    adminActivateCount += 1;
    return {'status': 'active'};
  }

  @override
  Future<Map<String, dynamic>> activateUserAutomationProfile(int profileId,
      {bool confirmOperatorAck = true}) async {
    userActivateCount += 1;
    return {'status': 'active'};
  }
}

Map<String, dynamic> _profileJson({
  int id = 1,
  String name = 'Shared profile',
}) {
  return {
    'id': id,
    'profile_key': 'shared-profile',
    'name': name,
    'provider': 'kis',
    'market': 'KR',
    'enabled': false,
    'status': 'disabled',
    'settings': {
      'capital': {
        'sizing_mode': 'equity_pct',
        'target_position_pct': 10,
        'max_position_pct': 12,
        'max_total_exposure_pct': 30,
        'max_order_notional_krw': 500000,
        'fixed_budget': 500000,
        'compound_enabled': false,
      },
      'universe': {'watchlist_size': 50},
      'entry': {
        'analysis_times': ['09:10', '11:30', '13:30'],
        'max_new_entries_per_day': 1,
      },
      'monitoring': {'interval_seconds': 60},
      'exit': {'stop_loss_pct': 2, 'take_profit_pct': 3},
      'operation': {
        'start_date': '2026-08-17',
        'end_date': '2026-09-18',
      },
      'max_open_positions': 1,
    },
  };
}
