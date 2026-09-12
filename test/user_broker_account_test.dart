import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/user/user_assets_screen.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/automation_strategy_profile.dart';
import 'package:auto_invest_dashboard/models/user_broker_account_snapshot.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';
import 'package:auto_invest_dashboard/models/user_watchlist_item.dart';

void main() {
  testWidgets('regular user automatically loads configured read-only assets',
      (tester) async {
    final api = _UserAccountApi(
      brokers: [
        const UserBrokerCredential(
          provider: 'kis',
          configured: true,
          environment: 'paper',
        ),
        const UserBrokerCredential(
          provider: 'alpaca',
          configured: false,
        ),
      ],
      snapshots: {'kis': _kisSnapshot()},
    );
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    expect(api.snapshotProviders, ['kis']);
    expect(controller.kisUserAccount?.connected, isTrue);
    expect(controller.kisUserAccount?.account.portfolioValue, 1050000);
    expect(controller.kisUserAccount?.positions.single.symbol, '005930');
    expect(controller.kisUserAccount?.openOrders, hasLength(1));
    expect(controller.alpacaUserAccount, isNull);
    expect(
      find.byKey(const ValueKey('home-account-connection-status')),
      findsOneWidget,
    );
    expect(find.text('\uC5F0\uACB0\uB428'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-portfolio-card')), findsOneWidget);
    expect(find.text('\u20A91,050,000'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('home-operation-mode-card')), findsOneWidget);
    final positions = find.byKey(const ValueKey('home-positions-card'));
    await tester.scrollUntilVisible(
      positions,
      500,
      scrollable: find
          .byWidgetPredicate(
            (widget) => widget is Scrollable,
          )
          .first,
    );
    await tester.pumpAndSettle();
    expect(positions, findsOneWidget);
    expect(find.textContaining('005930'), findsWidgets);
    expect(find.byKey(const ValueKey('home-open-admin')), findsNothing);

    final destinations = tester
        .widgetList<NavigationDestination>(
          find.byType(NavigationDestination),
        )
        .toList();
    expect(
      destinations.map((destination) => destination.label).toList(),
      [
        controller.strings.home,
        controller.strings.aiAssistant,
        controller.strings.assets,
      ],
    );

    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.byIcon(Icons.auto_awesome_outlined),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('ai-v2-welcome-card')), findsOneWidget);
    expect(find.byKey(const ValueKey('ai-open-admin')), findsNothing);

    await tester.tap(
      find.descendant(
        of: find.byType(NavigationBar),
        matching: find.byIcon(Icons.account_balance_wallet_outlined),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('user-assets-screen')), findsOneWidget);
    expect(
      find.byKey(const ValueKey('portfolio_snapshot_section')),
      findsOneWidget,
    );
    expect(find.text('\uC790\uC0B0 \uD604\uD669'), findsOneWidget);
    expect(find.text('\uBBF8\uCCB4\uACB0 \uC8FC\uBB38'), findsOneWidget);
    expect(find.text('\uCD1D\uC790\uC0B0'), findsOneWidget);
    expect(find.text('\uC608\uC218\uAE08'), findsOneWidget);
    expect(find.text('\uB9E4\uC218\uAC00\uB2A5\uAE08\uC561'), findsOneWidget);
    expect(find.text('\uD3C9\uAC00\uC190\uC775'), findsWidgets);
    expect(find.text('Prepare Manual Sell Ticket'), findsNothing);
    expect(find.text('Submit'), findsNothing);
    expect(find.text('Cancel'), findsNothing);
  });

  testWidgets('regular user with no configured broker sees safe empty state',
      (tester) async {
    final api = _UserAccountApi();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    expect(api.snapshotProviders, isEmpty);
    expect(controller.kisUserAccountError, 'broker_credentials_not_configured');
    expect(
      controller.alpacaUserAccountError,
      'broker_credentials_not_configured',
    );
    expect(find.text('계좌 미설정'), findsOneWidget);
    expect(find.byKey(const ValueKey('home-account-connect')), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('home-account-connect')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('user-settings-screen')), findsOneWidget);
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
    expect(
      brokerCard,
      findsOneWidget,
    );
  });

  testWidgets('regular Home opens the shared full automation profile editor',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(800, 1400));
    addTearDown(() async {
      await tester.binding.setSurfaceSize(null);
    });
    final api = _UserModeApi();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    final configure =
        find.byKey(const ValueKey('home-open-automation-profile'));
    await tester.scrollUntilVisible(
      configure,
      500,
      scrollable: find
          .byWidgetPredicate(
            (widget) => widget is Scrollable,
          )
          .first,
    );
    await tester.tap(configure);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('user-settings-screen')), findsNothing);
    expect(
      find.byKey(const ValueKey('automation-profile-editor')),
      findsOneWidget,
    );
    expect(find.text('자동화 프로필'), findsOneWidget);
    expect(
        find.byKey(const ValueKey('automation-profile-name')), findsOneWidget);
    expect(find.byKey(const ValueKey('automation-profile-start-date')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('automation-profile-max-exposure-pct')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('automation-profile-trading-mode')),
        findsNothing);
    await tester.enterText(
      find.byKey(const ValueKey('automation-profile-name')),
      'User profile',
    );
    final profileScrollView =
        find.byKey(const ValueKey('automation-profile-scroll-view'));
    for (var i = 0; i < 8; i += 1) {
      final saveRect = tester.getRect(
        find.byKey(const ValueKey('automation-profile-save')),
      );
      final viewport = tester.getRect(profileScrollView);
      if (saveRect.top >= viewport.top && saveRect.bottom <= viewport.bottom) {
        break;
      }
      await tester.drag(profileScrollView, const Offset(0, -600));
      await tester.pumpAndSettle();
    }
    await tester.tap(
      find.byKey(const ValueKey('automation-profile-save')),
    );
    await tester.pumpAndSettle();
    expect(api.userProfileCreates, 1);
    expect(api.adminProfileFetches, 0);
  });

  testWidgets(
      'regular Home hides account CTA after the selected broker is connected',
      (tester) async {
    final api = _UserAccountApi(
      brokers: [
        const UserBrokerCredential(
          provider: 'kis',
          configured: true,
          environment: 'paper',
        ),
      ],
      snapshots: {'kis': _kisSnapshot()},
    );
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('home-account-connect')), findsNothing);
    expect(find.text('연결됨'), findsOneWidget);
  });

  testWidgets('regular Home persists its mode through user trading settings',
      (tester) async {
    final api = _UserModeApi();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    await tester
        .tap(find.byKey(const ValueKey('home-operation-mode-selector')));
    await tester.pumpAndSettle();
    expect(
      find.byKey(const ValueKey('home-operation-mode-live')),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('home-operation-mode-live')));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('home-operation-mode-apply')));
    await tester.pumpAndSettle();
    await tester.tap(
      find.byKey(const ValueKey('home-operation-mode-live-confirm')),
    );
    await tester.pumpAndSettle();

    expect(api.modeUpdates, ['live']);
    expect(find.text('실거래'), findsWidgets);
  });

  testWidgets('user Assets renders account data without trading controls',
      (tester) async {
    final controller = DashboardController(
      _UserAccountApi(),
      autoload: false,
    );
    controller.userBrokerCredentials = [
      const UserBrokerCredential(
        provider: 'kis',
        configured: true,
        environment: 'paper',
      ),
    ];
    controller.kisUserAccount = _kisSnapshot();
    controller.kisUserAccountLoading = false;
    controller.alpacaUserAccountError = 'broker_credentials_not_configured';

    await tester.pumpWidget(
      MaterialApp(home: UserAssetsScreen(controller: controller)),
    );

    expect(find.text('\uC5F0\uACB0\uB428'), findsOneWidget);
    expect(find.text('\u20A91,050,000'), findsOneWidget);
    expect(find.text('005930'), findsOneWidget);
    expect(find.text('\uBBF8\uCCB4\uACB0 \uC8FC\uBB38'), findsOneWidget);
    expect(find.text('Prepare Manual Sell Ticket'), findsNothing);
    expect(find.text('Submit'), findsNothing);
    expect(find.text('Cancel'), findsNothing);
    controller.dispose();
  });

  testWidgets('regular Assets uses shared admin-style USD formatting',
      (tester) async {
    final controller = DashboardController(
      _UserAccountApi(),
      autoload: false,
    );
    controller.userBrokerCredentials = [
      const UserBrokerCredential(
        provider: 'alpaca',
        configured: true,
        environment: 'paper',
      ),
    ];
    controller.alpacaUserAccount = _alpacaSnapshot();
    controller.alpacaUserAccountLoading = false;

    await tester.pumpWidget(
      MaterialApp(home: UserAssetsScreen(controller: controller)),
    );
    await tester.tap(
      find.byKey(const ValueKey('broker-option-alpaca-label')),
    );
    await tester.pumpAndSettle();

    expect(find.text('Alpaca / \uBBF8\uAD6D \uACC4\uC88C'), findsOneWidget);
    expect(find.text(r'$1,200.00'), findsWidgets);
    expect(find.text(r'$500.00'), findsWidgets);
    expect(find.text(r'+$200.00'), findsWidgets);
    expect(find.text('\uB9E4\uC218'), findsOneWidget);
    expect(find.text('Prepare Manual Sell Ticket'), findsNothing);
    controller.dispose();
  });
}

UserBrokerAccountSnapshot _kisSnapshot() {
  return UserBrokerAccountSnapshot.fromJson({
    'provider': 'kis',
    'environment': 'paper',
    'connected': true,
    'connection_status': 'connected',
    'fetched_at': '2099-01-01T00:00:00Z',
    'account': {
      'currency': 'KRW',
      'cash': 1000000,
      'buying_power': 350000,
      'equity': 1050000,
      'portfolio_value': 1050000,
      'unrealized_pl': 35000,
      'unrealized_pl_pct': 5,
    },
    'positions': [
      {
        'symbol': '005930',
        'name': '\uC0BC\uC131\uC804\uC790',
        'quantity': 10,
        'available_quantity': 10,
        'avg_price': 70000,
        'current_price': 72000,
        'market_value': 720000,
        'cost_basis': 700000,
        'unrealized_pl': 20000,
        'unrealized_pl_pct': 2.857,
      },
    ],
    'open_orders': [
      {
        'broker_order_id': 'order-1',
        'symbol': '005930',
        'side': 'buy',
        'quantity': 4,
        'filled_quantity': 1,
        'remaining_quantity': 3,
        'order_price': 71000,
        'status': 'pending',
      },
    ],
  });
}

UserBrokerAccountSnapshot _alpacaSnapshot() {
  return UserBrokerAccountSnapshot.fromJson({
    'provider': 'alpaca',
    'environment': 'paper',
    'connected': true,
    'connection_status': 'connected',
    'account': {
      'currency': 'USD',
      'cash': 500,
      'buying_power': 500,
      'equity': 1700,
      'portfolio_value': 1700,
      'unrealized_pl': 200,
      'unrealized_pl_pct': 20,
    },
    'positions': [
      {
        'symbol': 'AAPL',
        'name': 'Apple',
        'quantity': 2,
        'avg_price': 500,
        'current_price': 600,
        'market_value': 1200,
        'cost_basis': 1000,
        'unrealized_pl': 200,
        'unrealized_pl_pct': 20,
      },
    ],
    'open_orders': [
      {
        'broker_order_id': 'alpaca-order-1',
        'symbol': 'AAPL',
        'side': 'buy',
        'quantity': 1,
        'filled_quantity': 0,
        'remaining_quantity': 1,
        'order_price': 590,
        'status': 'pending',
      },
    ],
  });
}

class _UserAccountApi extends ApiClient {
  _UserAccountApi({
    this.brokers = const [],
    this.snapshots = const {},
  });

  final List<UserBrokerCredential> brokers;
  final Map<String, UserBrokerAccountSnapshot> snapshots;
  final List<String> snapshotProviders = [];

  @override
  Future<AuthSessionState> fetchAuthMe() async {
    return const AuthSessionState(
      authenticated: true,
      setupRequired: false,
      user: AuthUser(
        username: 'user01',
        role: 'user',
        enabled: true,
        setupCompleted: true,
      ),
    );
  }

  @override
  Future<List<UserBrokerCredential>> fetchUserBrokers() async => brokers;

  @override
  Future<UserBrokerAccountSnapshot> getMyBrokerAccountSnapshot(
    String provider,
  ) async {
    snapshotProviders.add(provider);
    return snapshots[provider]!;
  }

  @override
  Future<Map<String, dynamic>> fetchUserSettings() async => {};

  @override
  Future<Map<String, dynamic>> fetchUserTradingSettings() async => {};

  @override
  Future<List<UserWatchlistItem>> fetchUserWatchlist() async => [];
}

class _UserModeApi extends _UserAccountApi {
  String mode = 'paper';
  final List<String> modeUpdates = [];
  final Map<String, dynamic> tradingSettings = {
    'trading_mode': 'paper',
    'live_trading_enabled': false,
    'kill_switch': true,
    'auto_trading_enabled': false,
    'max_daily_trades': 2,
    'max_daily_loss_pct': 0.02,
    'max_position_pct': 10,
    'max_open_positions': 1,
  };
  final List<Map<String, dynamic>> tradingUpdates = [];
  int userProfileFetches = 0;
  int userProfileCreates = 0;
  int adminProfileFetches = 0;

  @override
  Future<AutomationStrategyProfileList> fetchUserAutomationProfiles() async {
    userProfileFetches += 1;
    return AutomationStrategyProfileList.fromJson({
      'profiles': <Map<String, dynamic>>[],
      'active_profile': null,
      'selected_profile': null,
      'selected_profile_status': null,
    });
  }

  @override
  Future<AutomationStrategyProfile> createUserAutomationProfile(
      Map<String, dynamic> body) async {
    userProfileCreates += 1;
    return AutomationStrategyProfile.fromJson({
      'id': 1,
      'profile_key': 'user-profile',
      'name': body['name'] ?? 'User profile',
      'provider': 'kis',
      'market': 'KR',
      'enabled': false,
      'status': 'disabled',
      'settings': _minimalProfileSettings(),
    });
  }

  @override
  Future<AutomationStrategyProfileList> fetchAutomationProfiles() async {
    adminProfileFetches += 1;
    throw StateError('Admin profile API must not be called for a regular user');
  }

  @override
  Future<Map<String, dynamic>> fetchUserTradingSettings() async =>
      Map<String, dynamic>.from(tradingSettings);

  @override
  Future<Map<String, dynamic>> updateUserTradingSettings({
    String? tradingMode,
    int? maxDailyTrades,
    double? maxDailyLossPct,
    double? maxPositionPct,
    int? maxOpenPositions,
    bool? liveTradingEnabled,
    bool? killSwitch,
    bool? autoTradingEnabled,
    String? autoTradingProvider,
    bool? autoLiveConfirmed,
    bool confirmAutoLive = false,
  }) async {
    if (tradingMode != null) {
      mode = tradingMode;
      modeUpdates.add(tradingMode);
      tradingSettings['trading_mode'] = tradingMode;
    }
    final update = <String, dynamic>{
      if (tradingMode != null) 'trading_mode': tradingMode,
      if (maxDailyTrades != null) 'max_daily_trades': maxDailyTrades,
      if (maxDailyLossPct != null) 'max_daily_loss_pct': maxDailyLossPct,
      if (maxPositionPct != null) 'max_position_pct': maxPositionPct,
      if (maxOpenPositions != null) 'max_open_positions': maxOpenPositions,
      if (liveTradingEnabled != null)
        'live_trading_enabled': liveTradingEnabled,
      if (killSwitch != null) 'kill_switch': killSwitch,
      if (autoTradingEnabled != null)
        'auto_trading_enabled': autoTradingEnabled,
      if (autoTradingProvider != null)
        'auto_trading_provider': autoTradingProvider,
      if (autoLiveConfirmed != null) 'auto_live_confirmed': autoLiveConfirmed,
      if (confirmAutoLive) 'confirm_auto_live': true,
    };
    tradingUpdates.add(update);
    tradingSettings.addAll(update);
    return Map<String, dynamic>.from(tradingSettings);
  }
}

Map<String, dynamic> _minimalProfileSettings() => {
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
    };
