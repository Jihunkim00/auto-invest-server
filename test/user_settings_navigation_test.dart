import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';
import 'package:auto_invest_dashboard/models/user_watchlist_item.dart';

void main() {
  testWidgets('regular user Home opens the existing broker Settings screen',
      (tester) async {
    final api = _RegularUserSettingsApiClient();
    final controller = DashboardController(api, autoload: false);
    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('home-open-settings')), findsOneWidget);
    expect(find.byKey(const ValueKey('home-open-admin')), findsNothing);
    expect(find.byType(NavigationDestination), findsNWidgets(3));
    expect(
      tester
          .widgetList<NavigationDestination>(
            find.byType(NavigationDestination),
          )
          .map((destination) => destination.label)
          .toList(),
      [
        controller.strings.home,
        controller.strings.aiAssistant,
        controller.strings.assets
      ],
    );

    await tester.tap(find.byKey(const ValueKey('home-open-settings')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('user-settings-screen')), findsOneWidget);
    final brokerCard = find.byKey(
      const ValueKey('user-broker-connections-card'),
    );
    await tester.scrollUntilVisible(
      brokerCard,
      500,
      scrollable: find.byWidgetPredicate(
        (widget) =>
            widget is Scrollable && widget.axisDirection == AxisDirection.down,
      ).first,
    );
    await tester.pumpAndSettle();
    expect(brokerCard, findsOneWidget);
    expect(
        find.byKey(const ValueKey('user-broker-kis-app-key')), findsOneWidget);
    expect(find.byKey(const ValueKey('user-broker-alpaca-api-key')),
        findsOneWidget);
    expect(find.text('증권사 연결'), findsOneWidget);
    expect(find.text('한국투자증권'), findsOneWidget);
    expect(find.text('Alpaca'), findsOneWidget);
  });
}

class _RegularUserSettingsApiClient extends ApiClient {
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
  Future<List<UserBrokerCredential>> fetchUserBrokers() async => [
        const UserBrokerCredential(provider: 'kis', configured: false),
        const UserBrokerCredential(provider: 'alpaca', configured: false),
      ];
}
