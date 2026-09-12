import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/user_broker_account_snapshot.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';
import 'package:auto_invest_dashboard/models/user_watchlist_item.dart';

void main() {
  testWidgets('user broker save refreshes Home with the user account',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() async {
      await tester.binding.setSurfaceSize(null);
    });
    final api = _HomeBrokerFlowApi();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('home-account-connect')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('home-account-connect')));
    await tester.pumpAndSettle();

    final brokerCard =
        find.byKey(const ValueKey('user-broker-connections-card'));
    await tester.scrollUntilVisible(
      brokerCard,
      500,
      scrollable: find
          .byWidgetPredicate(
            (widget) =>
                widget is Scrollable &&
                widget.axisDirection == AxisDirection.down,
          )
          .first,
    );
    await tester.pumpAndSettle();
    expect(brokerCard, findsOneWidget);

    const fields = {
      'user-broker-kis-app-key': 'user-app-key',
      'user-broker-kis-app-secret': 'user-app-secret',
      'user-broker-kis-hts-id': 'user-hts-id',
      'user-broker-kis-account-no': '12345678',
      'user-broker-kis-product-code': '01',
    };
    for (final entry in fields.entries) {
      await tester.enterText(find.byKey(ValueKey(entry.key)), entry.value);
    }

    final save = find.byKey(const ValueKey('user-broker-kis-save'));
    await tester.scrollUntilVisible(
      save,
      500,
      scrollable: find
          .byWidgetPredicate(
            (widget) =>
                widget is Scrollable &&
                widget.axisDirection == AxisDirection.down,
          )
          .first,
    );
    await tester.tap(save);
    await tester.pumpAndSettle();

    expect(api.savedCredentials.single['app_key'], 'user-app-key');
    expect(api.savedCredentials.single['app_secret'], 'user-app-secret');
    expect(api.snapshotCalls, greaterThan(0));

    await tester.tap(find.byType(BackButton));
    await tester.pumpAndSettle();
    expect(controller.kisUserAccount?.connected, isTrue);
    expect(find.text('연결됨'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-account-connect')), findsNothing);
  });
}

class _HomeBrokerFlowApi extends ApiClient {
  bool configured = false;
  final List<Map<String, dynamic>> savedCredentials = [];
  int snapshotCalls = 0;

  @override
  Future<AuthSessionState> fetchAuthMe() async => const AuthSessionState(
        authenticated: true,
        setupRequired: false,
        user: AuthUser(
          username: 'regular-user',
          role: 'user',
          enabled: true,
          setupCompleted: true,
        ),
      );

  @override
  Future<Map<String, dynamic>> fetchUserSettings() async => {};

  @override
  Future<List<UserWatchlistItem>> fetchUserWatchlist() async => [];

  @override
  Future<Map<String, dynamic>> fetchUserTradingSettings() async => {
        'trading_mode': 'paper',
        'live_trading_enabled': false,
        'kill_switch': true,
        'auto_trading_enabled': false,
        'max_daily_trades': 2,
        'max_daily_loss_pct': 0.02,
        'max_position_pct': 10,
        'max_open_positions': 1,
      };

  @override
  Future<List<UserBrokerCredential>> fetchUserBrokers() async => [
        UserBrokerCredential(provider: 'kis', configured: configured),
        const UserBrokerCredential(provider: 'alpaca', configured: false),
      ];

  @override
  Future<UserBrokerCredential> saveUserBroker(
    String provider,
    Map<String, dynamic> credentials,
  ) async {
    configured = true;
    savedCredentials.add(credentials);
    return const UserBrokerCredential(
      provider: 'kis',
      configured: true,
      environment: 'paper',
    );
  }

  @override
  Future<UserBrokerAccountSnapshot> getMyBrokerAccountSnapshot(
    String provider,
  ) async {
    snapshotCalls += 1;
    return UserBrokerAccountSnapshot.fromJson({
      'provider': provider,
      'environment': 'paper',
      'connected': true,
      'connection_status': 'connected',
      'account': {
        'currency': 'KRW',
        'cash': 1000000,
        'buying_power': 1000000,
        'equity': 1000000,
        'portfolio_value': 1000000,
      },
      'positions': [],
      'open_orders': [],
    });
  }
}
