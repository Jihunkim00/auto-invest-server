import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/app.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/storage_provider_preference.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/automation_strategy_profile.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';
import 'package:auto_invest_dashboard/models/market_regime.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';

import 'package:auto_invest_dashboard/models/user_broker_account_snapshot.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';

void main() {
  testWidgets('admin still uses the existing dashboard load and KIS regime',
      (tester) async {
    final api = _RegularUserApi(role: 'admin');
    final controller = _AdminDashboardController(api, autoload: false);

    await tester.pumpWidget(
      AutoInvestApp(
        controller: controller,
        authenticationEnabled: true,
      ),
    );
    await tester.pumpAndSettle();

    expect(controller.loadCalls, 1);
    expect(api.adminPortfolioReads, 1);
    expect(api.marketRegimeCalls, 1);
    expect(api.snapshotProviders, isEmpty);
  });

  testWidgets(
      'regular user restores owner context before KIS account and regime load without F5',
      (tester) async {
    final api = _RegularUserApi();
    final controller = await _mountRegularUser(tester, api);

    expect(api.contextReadyWhenAccountStarted, isTrue);
    expect(api.ownerAtAccountRequests, [17]);
    expect(api.providerAtAccountRequests, [SelectedProvider.kis]);
    expect(api.marketAtAccountRequests, [PortfolioMarket.kr]);
    expect(api.snapshotProviders, ['kis']);
    expect(api.marketRegimeCalls, 1);
    expect(controller.kisUserAccount?.connected, isTrue);
    expect(controller.marketRegime?.marketScore, 61.23);
    expect(api.adminPortfolioReads, 0);
    expect(api.settingsCalls, greaterThanOrEqualTo(1));
    expect(find.byKey(const ValueKey('home-account-state-loaded')),
        findsOneWidget);

    controller.notifyListeners();
    await tester.pump();
    await controller.bootstrapRegularUserHome(api.user);
    expect(api.snapshotProviders, ['kis']);
    expect(api.userBrokerCalls, 1);
    expect(api.marketRegimeCalls, 1);
  });

  testWidgets('KIS account waits for asynchronous user provider restoration',
      (tester) async {
    final provider = Completer<String?>();
    final store = _DeferredUserProviderStore(provider);
    final api = _RegularUserApi();
    final controller = await _mountRegularUser(
      tester,
      api,
      persistProvider: true,
      providerPreferenceStore: store,
    );

    expect(store.readScopes, ['id-17']);
    expect(api.snapshotProviders, isEmpty);
    expect(api.marketRegimeCalls, 0);
    expect(controller.regularUserHomeContextReady, isFalse);

    provider.complete('kis');
    await tester.pumpAndSettle();

    expect(controller.regularUserHomeContextReady, isTrue);
    expect(api.snapshotProviders, ['kis']);
    expect(api.marketRegimeCalls, 1);
    expect(controller.kisUserAccount?.connected, isTrue);
  });

  testWidgets('market regime can finish before the KIS account read',
      (tester) async {
    final account = Completer<UserBrokerAccountSnapshot>();
    final api = _RegularUserApi(
      accountLoader: (_, __) => account.future,
    );
    final controller = await _mountRegularUser(tester, api);

    expect(controller.marketRegimeLoaded, isTrue);
    expect(controller.kisUserAccount, isNull);
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.loading);
    expect(find.byKey(const ValueKey('home-account-state-loading')),
        findsOneWidget);

    account.complete(_snapshot('kis'));
    await tester.pumpAndSettle();
    expect(controller.kisUserAccount?.connected, isTrue);
    expect(find.byKey(const ValueKey('home-account-state-loaded')),
        findsOneWidget);
  });

  testWidgets('KIS account can finish before the market regime read',
      (tester) async {
    final regime = Completer<MarketRegime>();
    final api = _RegularUserApi(
      regimeLoader: () => regime.future,
    );
    final controller = await _mountRegularUser(tester, api);

    expect(controller.kisUserAccount?.connected, isTrue);
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.loaded);
    expect(controller.marketRegime, isNull);
    expect(controller.marketRegimeLoading, isTrue);
    expect(find.byKey(const ValueKey('home-account-state-loaded')),
        findsOneWidget);

    regime.complete(_marketRegime());
    await tester.pumpAndSettle();
    expect(controller.marketRegime?.marketScore, 61.23);
  });

  testWidgets('market regime failure does not block the KIS account',
      (tester) async {
    final api = _RegularUserApi(
      regimeLoader: () => Future<MarketRegime>.error(StateError('offline')),
    );
    final controller = await _mountRegularUser(tester, api);

    expect(controller.marketRegimeLoaded, isTrue);
    expect(controller.marketRegimeError, isNotNull);
    expect(controller.kisUserAccount?.connected, isTrue);
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.loaded);
  });

  testWidgets('KIS transient HTTP 500 retries once and then publishes data',
      (tester) async {
    final secondRead = Completer<UserBrokerAccountSnapshot>();
    final api = _RegularUserApi(
      accountLoader: (_, attempt) {
        if (attempt == 1) {
          throw const ApiRequestException('temporary failure', statusCode: 500);
        }
        return secondRead.future;
      },
    );
    final controller = await _mountRegularUser(tester, api);

    await tester.pump(const Duration(milliseconds: 50));
    expect(api.snapshotProviders, hasLength(1));
    expect(api.snapshotProviders.single, 'kis');
    expect(controller.kisUserAccountLoadState,
        UserBrokerAccountLoadState.transientRetrying);
    expect(
        find.byKey(
          const ValueKey('home-account-state-transientRetrying'),
        ),
        findsOneWidget);

    await tester.pump(const Duration(milliseconds: 300));
    expect(api.snapshotProviders, ['kis', 'kis']);
    expect(controller.kisUserAccountLoadState,
        UserBrokerAccountLoadState.transientRetrying);

    secondRead.complete(_snapshot('kis'));
    await tester.pumpAndSettle();
    expect(controller.kisUserAccount?.connected, isTrue);
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.loaded);
    expect(find.byKey(const ValueKey('home-account-state-loaded')),
        findsOneWidget);
  });

  testWidgets('KIS timeout receives one bounded read retry', (tester) async {
    final secondRead = Completer<UserBrokerAccountSnapshot>();
    final api = _RegularUserApi(
      accountLoader: (_, attempt) {
        if (attempt == 1) throw TimeoutException('read timed out');
        return secondRead.future;
      },
    );
    final controller = await _mountRegularUser(tester, api);

    expect(api.snapshotProviders, ['kis']);
    expect(controller.kisUserAccountLoadState,
        UserBrokerAccountLoadState.transientRetrying);
    await tester.pump(const Duration(milliseconds: 350));
    expect(api.snapshotProviders, ['kis', 'kis']);

    secondRead.complete(_snapshot('kis'));
    await tester.pumpAndSettle();
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.loaded);
  });

  testWidgets('KIS authorization failure is not retried', (tester) async {
    final api = _RegularUserApi(
      accountLoader: (_, __) => Future<UserBrokerAccountSnapshot>.error(
        const ApiRequestException('authentication failed', statusCode: 401),
      ),
    );
    final controller = await _mountRegularUser(tester, api);

    expect(api.snapshotProviders, ['kis']);
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.error);
    await tester.pump(const Duration(milliseconds: 500));
    expect(api.snapshotProviders, ['kis']);
  });

  testWidgets('KIS authorization and business errors are not retried',
      (tester) async {
    final api = _RegularUserApi(
      accountLoader: (_, __) => Future<UserBrokerAccountSnapshot>.error(
        const ApiRequestException('invalid request', statusCode: 422),
      ),
    );
    final controller = await _mountRegularUser(tester, api);

    expect(api.snapshotProviders, ['kis']);
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.error);
    await tester.pump(const Duration(milliseconds: 500));
    expect(api.snapshotProviders, ['kis']);
  });

  testWidgets(
      'second KIS account read failure is deterministic and leaves regime visible',
      (tester) async {
    final api = _RegularUserApi(
      accountLoader: (_, __) => Future<UserBrokerAccountSnapshot>.error(
        const ApiRequestException('temporary failure', statusCode: 503),
      ),
    );
    final controller = await _mountRegularUser(tester, api);

    await tester.pumpAndSettle();

    if (api.snapshotProviders.length < 2) {
      await tester.pump(const Duration(milliseconds: 400));
    }
    expect(api.snapshotProviders, ['kis', 'kis']);
    expect(controller.kisUserAccount, isNull);
    expect(controller.kisUserAccountError, 'broker_unavailable');
    expect(
        controller.kisUserAccountLoadState, UserBrokerAccountLoadState.error);
    expect(controller.marketRegime?.marketScore, 61.23);
    expect(
        find.byKey(const ValueKey('home-account-state-error')), findsOneWidget);
  });

  testWidgets('authentication and rebuild do not duplicate user reads',
      (tester) async {
    final api = _RegularUserApi();
    final controller = await _mountRegularUser(tester, api);

    controller.notifyListeners();
    await tester.pump();
    await controller.bootstrapRegularUserHome(api.user);

    expect(api.authCalls, 1);
    expect(api.userBrokerCalls, 1);
    expect(api.profileCalls, 1);
    expect(api.snapshotProviders, ['kis']);
    expect(api.marketRegimeCalls, 1);
  });

  testWidgets('Alpaca regular-user bootstrap remains user scoped',
      (tester) async {
    final api = _RegularUserApi(
      brokers: const [
        UserBrokerCredential(provider: 'alpaca', configured: true),
      ],
      profileProvider: 'alpaca',
      profileMarket: 'US',
    );
    final controller = await _mountRegularUser(tester, api);

    expect(controller.selectedProvider, SelectedProvider.alpaca);
    expect(api.snapshotProviders, ['alpaca']);
    expect(api.ownerAtAccountRequests, [17]);
    expect(api.marketRegimeCalls, 0);
    expect(controller.alpacaUserAccount?.connected, isTrue);
    expect(controller.alpacaUserAccountLoadState,
        UserBrokerAccountLoadState.loaded);
  });
}

Future<DashboardController> _mountRegularUser(
  WidgetTester tester,
  _RegularUserApi api, {
  bool persistProvider = false,
  ProviderPreferenceStore? providerPreferenceStore,
}) async {
  final controller = DashboardController(
    api,
    autoload: false,
    persistProvider: persistProvider,
    providerPreferenceStore: providerPreferenceStore,
  );
  api.controller = controller;
  await tester.pumpWidget(
    AutoInvestApp(
      controller: controller,
      authenticationEnabled: true,
    ),
  );
  await tester.pump();
  for (var frame = 0; frame < 5; frame += 1) {
    await tester.pump(const Duration(milliseconds: 25));
  }
  return controller;
}

class _RegularUserApi extends ApiClient {
  _RegularUserApi({
    this.role = 'user',
    this.brokers = const [
      UserBrokerCredential(provider: 'kis', configured: true),
    ],
    this.profileProvider = 'kis',
    this.profileMarket = 'KR',
    this.accountLoader,
    this.regimeLoader,
  });

  final String role;
  final List<UserBrokerCredential> brokers;
  final String? profileProvider;
  final String profileMarket;
  final Future<UserBrokerAccountSnapshot> Function(String, int)? accountLoader;
  final Future<MarketRegime> Function()? regimeLoader;
  final List<String> events = [];
  final List<String> snapshotProviders = [];
  final List<int?> ownerAtAccountRequests = [];
  final List<SelectedProvider> providerAtAccountRequests = [];
  final List<PortfolioMarket> marketAtAccountRequests = [];
  DashboardController? controller;
  int authCalls = 0;
  int settingsCalls = 0;
  int userBrokerCalls = 0;
  int profileCalls = 0;
  int marketRegimeCalls = 0;
  int adminPortfolioReads = 0;
  final Map<String, int> _accountAttempts = {};

  AuthUser get user => AuthUser(
        id: 17,
        username: role == 'admin' ? 'admin01' : 'test01',
        role: role,
        enabled: true,
        setupCompleted: true,
      );

  bool get contextReadyWhenAccountStarted =>
      events.contains('settings:done') &&
      events.contains('brokers:done') &&
      events.contains('profiles:done');

  @override
  Future<AuthSessionState> fetchAuthMe() async {
    authCalls += 1;
    events.add('auth:done');
    return AuthSessionState(
      authenticated: true,
      setupRequired: false,
      user: user,
    );
  }

  @override
  Future<Map<String, dynamic>> fetchUserTradingSettings() async {
    settingsCalls += 1;
    events.add('settings:done');
    return const {'trading_mode': 'paper'};
  }

  @override
  Future<List<UserBrokerCredential>> fetchUserBrokers() async {
    userBrokerCalls += 1;
    events.add('brokers:done');
    return brokers;
  }

  @override
  Future<AutomationStrategyProfileList> fetchUserAutomationProfiles() async {
    profileCalls += 1;
    events.add('profiles:done');
    return AutomationStrategyProfileList.fromJson({
      'profiles': <Map<String, dynamic>>[],
      'selected_profile': profileProvider == null
          ? null
          : {
              'id': 2,
              'profile_key': 'test01-profile',
              'name': 'test01 profile',
              'provider': profileProvider,
              'market': profileMarket,
              'enabled': false,
              'status': 'disabled',
              'settings': <String, dynamic>{},
            },
    });
  }

  @override
  Future<UserBrokerAccountSnapshot> getMyBrokerAccountSnapshot(
    String provider,
  ) {
    snapshotProviders.add(provider);
    events.add('account:$provider:start');
    ownerAtAccountRequests.add(controller?.authenticatedRegularOwnerUserId);
    providerAtAccountRequests.add(controller!.selectedProvider);
    marketAtAccountRequests.add(controller!.selectedPortfolioMarket);
    final attempt = (_accountAttempts[provider] ?? 0) + 1;
    _accountAttempts[provider] = attempt;
    return accountLoader?.call(provider, attempt) ??
        Future<UserBrokerAccountSnapshot>.value(_snapshot(provider));
  }

  @override
  Future<MarketRegime> fetchMarketRegime() {
    marketRegimeCalls += 1;
    events.add('regime:start');
    return regimeLoader?.call() ?? Future<MarketRegime>.value(_marketRegime());
  }

  @override
  Future<List<TradingLogItem>> fetchUserTradingRuns({int limit = 20}) async =>
      const [];

  @override
  Future<AutomationTodayDecisions> fetchUserTodayAiDecisions() async =>
      AutomationTodayDecisions.empty;

  @override
  Future<PortfolioSummary> fetchKrPortfolioSummary() async {
    adminPortfolioReads += 1;
    return PortfolioSummary.empty(currency: 'KRW');
  }

  @override
  Future<PortfolioSummary> fetchPortfolioSummary() async {
    adminPortfolioReads += 1;
    return PortfolioSummary.empty(currency: 'USD');
  }
}

class _DeferredUserProviderStore extends ProviderPreferenceStore {
  _DeferredUserProviderStore(this.provider);

  final Completer<String?> provider;
  final List<String> readScopes = [];

  @override
  Future<String?> readForUser(String userScope) {
    readScopes.add(userScope);
    return provider.future;
  }

  @override
  Future<void> writeForUser(String userScope, String value) async {}
}

class _AdminDashboardController extends DashboardController {
  _AdminDashboardController(super.apiClient, {super.autoload = false});

  int loadCalls = 0;

  @override
  Future<void> load() async {
    loadCalls += 1;
    await apiClient.fetchKrPortfolioSummary();
    await loadMarketRegime();
  }
}

UserBrokerAccountSnapshot _snapshot(String provider) =>
    UserBrokerAccountSnapshot.fromJson({
      'provider': provider,
      'environment': 'paper',
      'connected': true,
      'connection_status': 'connected',
      'account': {
        'currency': provider == 'kis' ? 'KRW' : 'USD',
        'cash': 350000,
        'buying_power': 350000,
        'equity': 1050000,
        'portfolio_value': 1050000,
      },
      'positions': [
        {
          'symbol': provider == 'kis' ? '005930' : 'AAPL',
          'name': provider == 'kis' ? 'Samsung' : 'Apple',
          'quantity': 1,
          'avg_price': 1000000,
          'current_price': 1050000,
          'market_value': 1050000,
          'cost_basis': 1000000,
          'unrealized_pl': 50000,
        },
      ],
      'open_orders': <Map<String, dynamic>>[],
    });

MarketRegime _marketRegime() => MarketRegime.fromJson({
      'status': 'confirmed',
      'stage': 4,
      'stage_label': 'uptrend',
      'short_label': 'up',
      'market_score': 61.23,
      'confirmed': true,
    });
