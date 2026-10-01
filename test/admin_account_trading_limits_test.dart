import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/admin/admin_account_detail_screen.dart';
import 'package:auto_invest_dashboard/features/admin/admin_user_management_panel.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';

const regular = AuthUser(
    id: 2,
    username: 'test01',
    role: 'user',
    enabled: true,
    setupCompleted: true);
const admin = AuthUser(
    id: 1,
    username: 'admin',
    role: 'admin',
    enabled: true,
    setupCompleted: true);
const second = AuthUser(
    id: 3,
    username: 'test02',
    role: 'user',
    enabled: true,
    setupCompleted: true);

Future<void> openDetail(WidgetTester tester, FakeAdminApi api,
    {AuthUser user = regular}) async {
  await tester.pumpWidget(
      MaterialApp(home: AdminAccountDetailScreen(apiClient: api, user: user)));
  await tester.pumpAndSettle();
}

Finder amount(String dimension) =>
    find.byKey(ValueKey('account-limit-$dimension-amount'));
Finder unlimited(String dimension) =>
    find.byKey(ValueKey('account-limit-$dimension-unlimited'));

void main() {
  testWidgets(
      'existing account management opens detail and trading-limit section',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AdminUserManagementPanel(apiClient: FakeAdminApi()))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('test01'));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('admin-account-detail')), findsOneWidget);
    expect(find.text('거래 한도'), findsOneWidget);
  });

  testWidgets('regular defaults render formatted KRW 10M and 1M',
      (tester) async {
    await openDetail(tester, FakeAdminApi());
    expect(find.text('10,000,000'), findsOneWidget);
    expect(find.text('1,000,000'), findsOneWidget);
    expect(tester.widget<TextFormField>(amount('total')).enabled, isTrue);
    expect(tester.widget<TextFormField>(amount('position')).enabled, isTrue);
  });

  testWidgets('admin unlimited renders and disables amount inputs',
      (tester) async {
    await openDetail(tester, FakeAdminApi(), user: admin);
    expect(find.text('제한 없음'), findsWidgets);
    expect(tester.widget<TextFormField>(amount('total')).enabled, isFalse);
    expect(tester.widget<TextFormField>(amount('position')).enabled, isFalse);
  });

  testWidgets('unlimited toggle disables numeric input', (tester) async {
    await openDetail(tester, FakeAdminApi());
    await tester.tap(unlimited('total'));
    await tester.pumpAndSettle();
    expect(tester.widget<TextFormField>(amount('total')).enabled, isFalse);
    expect(tester.widget<TextFormField>(amount('position')).enabled, isTrue);
  });

  testWidgets('unlimited saves explicit null', (tester) async {
    final api = FakeAdminApi();
    await openDetail(tester, api);
    await tester.tap(unlimited('total'));
    await tester.tap(unlimited('position'));
    await tester.tap(find.byKey(const ValueKey('account-limit-save')));
    await tester.pumpAndSettle();
    expect(api.lastSaved,
        {'max_total_exposure_krw': null, 'max_position_notional_krw': null});
    expect(api.savedUserId, 2);
  });

  testWidgets('finite amounts save numbers', (tester) async {
    final api = FakeAdminApi();
    await openDetail(tester, api);
    await tester.enterText(amount('total'), '20000000');
    await tester.enterText(amount('position'), '2000000');
    await tester.tap(find.byKey(const ValueKey('account-limit-save')));
    await tester.pumpAndSettle();
    expect(api.lastSaved, {
      'max_total_exposure_krw': 20000000.0,
      'max_position_notional_krw': 2000000.0
    });
    expect(find.text('20,000,000'), findsOneWidget);
  });

  testWidgets('failed save rolls back inputs to backend configuration',
      (tester) async {
    final api = FakeAdminApi()..failSave = true;
    await openDetail(tester, api);
    await tester.enterText(amount('total'), '20000000');
    await tester.tap(unlimited('position'));
    await tester.tap(find.byKey(const ValueKey('account-limit-save')));
    await tester.pumpAndSettle();
    expect(find.text('10,000,000'), findsOneWidget);
    expect(find.text('1,000,000'), findsOneWidget);
    expect(tester.widget<TextFormField>(amount('position')).enabled, isTrue);
    expect(find.byKey(const ValueKey('account-limit-error')), findsOneWidget);
  });

  testWidgets('refresh GET restores server truth after an external update',
      (tester) async {
    final api = FakeAdminApi();
    await openDetail(tester, api);
    await tester.enterText(amount('total'), '999');
    api.limits[2] = {
      'max_total_exposure_krw': 15000000.0,
      'max_position_notional_krw': null
    };
    await tester.tap(find.byKey(const ValueKey('account-limit-refresh')));
    await tester.pumpAndSettle();
    expect(find.text('15,000,000'), findsOneWidget);
    expect(tester.widget<TextFormField>(amount('position')).enabled, isFalse);
  });

  testWidgets('saving one account does not visually mutate another',
      (tester) async {
    final api = FakeAdminApi();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: AdminUserManagementPanel(apiClient: api))));
    await tester.pumpAndSettle();
    await tester.tap(find.text('test01'));
    await tester.pumpAndSettle();
    await tester.tap(unlimited('total'));
    await tester.tap(find.byKey(const ValueKey('account-limit-save')));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    await tester.tap(find.text('test02'));
    await tester.pumpAndSettle();
    expect(find.text('10,000,000'), findsOneWidget);
    expect(tester.widget<TextFormField>(amount('total')).enabled, isTrue);
    expect(api.limits[1]!['max_total_exposure_krw'], isNull);
  });

  testWidgets('non-admin context has no account editing controls or requests',
      (tester) async {
    final api = FakeAdminApi();
    await tester.pumpWidget(MaterialApp(
        home: AdminUserManagementPanel(
            apiClient: api, canManageAccounts: false)));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('admin-user-management')), findsNothing);
    expect(find.byKey(const ValueKey('account-limit-save')), findsNothing);
    expect(api.listCalls, 0);
  });

  testWidgets('existing activation switch remains independent of limits',
      (tester) async {
    final api = FakeAdminApi();
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: AdminUserManagementPanel(apiClient: api))));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('admin-user-status-2')));
    await tester.pumpAndSettle();
    expect(api.statusUpdates, [(2, false)]);
    expect(api.lastSaved, isNull);
    expect(
        tester
            .widget<Switch>(find.byKey(const ValueKey('admin-user-status-2')))
            .value,
        isFalse);
  });

  testWidgets('usage failure does not prevent editing configured limits',
      (tester) async {
    await openDetail(tester, FakeAdminApi()..failUsage = true);
    expect(find.text('10,000,000'), findsOneWidget);
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const ValueKey('account-limit-save')))
            .onPressed,
        isNotNull);
    expect(
        find.text('현재 사용 현황을 조회할 수 없습니다. 한도 설정은 변경할 수 있습니다.'), findsOneWidget);
  });
}

class FakeAdminApi extends ApiClient {
  final Map<int, Map<String, dynamic>> limits = {
    1: {'max_total_exposure_krw': null, 'max_position_notional_krw': null},
    2: {
      'max_total_exposure_krw': 10000000.0,
      'max_position_notional_krw': 1000000.0
    },
    3: {
      'max_total_exposure_krw': 10000000.0,
      'max_position_notional_krw': 1000000.0
    },
  };
  bool failSave = false;
  bool failUsage = false;
  int listCalls = 0;
  int? savedUserId;
  Map<String, dynamic>? lastSaved;
  List<(int, bool)> statusUpdates = [];

  @override
  Future<List<AuthUser>> fetchAdminUsers() async {
    listCalls++;
    return [admin, regular, second];
  }

  @override
  Future<Map<String, dynamic>> fetchAdminAccountDetail(int userId) async =>
      {'trading_limits': Map<String, dynamic>.from(limits[userId]!)};

  @override
  Future<Map<String, dynamic>> fetchAdminAccountLimitUsage(int userId) async {
    if (failUsage) throw Exception('Temporary positions failure');
    return {'available': false};
  }

  @override
  Future<Map<String, dynamic>> updateAdminAccountTradingLimits(
      {required int userId,
      required double? maxTotalExposureKrw,
      required double? maxPositionNotionalKrw}) async {
    if (failSave) throw Exception('Save failed');
    savedUserId = userId;
    lastSaved = {
      'max_total_exposure_krw': maxTotalExposureKrw,
      'max_position_notional_krw': maxPositionNotionalKrw
    };
    limits[userId] = Map.from(lastSaved!);
    return fetchAdminAccountDetail(userId);
  }

  @override
  Future<AuthUser> updateAdminUserStatus(
      {required int userId, required bool enabled}) async {
    statusUpdates.add((userId, enabled));
    return AuthUser(
        id: userId,
        username: 'test01',
        role: 'user',
        enabled: enabled,
        setupCompleted: true);
  }
}
