import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/automation_today_decisions.dart';
import 'package:auto_invest_dashboard/models/log_items.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/user_broker_account_snapshot.dart';
import 'package:auto_invest_dashboard/models/user_broker_credential.dart';

const user = AuthUser(
    id: 17,
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

void main() {
  test('logout then admin replaces every account-derived session state', () {
    final regular = DashboardController(_SessionApi(),
        autoload: false, initialLanguage: AppLanguage.english);
    expect(regular.beginAuthenticatedSession(user), same(regular));
    _seedAccountState(regular);
    final loggedOut = regular.clearAuthenticatedSession();
    final administrator = loggedOut.beginAuthenticatedSession(admin);
    addTearDown(regular.dispose);
    addTearDown(administrator.dispose);
    expect(administrator, isNot(same(regular)));
    _expectCleanSession(administrator);
    expect(administrator.appLanguage, AppLanguage.english);
  });

  test('admin to regular and direct identity changes start clean', () {
    var current = DashboardController(_SessionApi(), autoload: false);
    current.beginAuthenticatedSession(admin);
    _seedAccountState(current);
    final previous = current;
    current = current.beginAuthenticatedSession(user);
    addTearDown(previous.dispose);
    addTearDown(current.dispose);
    _expectCleanSession(current);
    expect(current, isNot(same(previous)));
  });

  test('same role id and username refresh preserves current state', () {
    final current = DashboardController(_SessionApi(), autoload: false);
    addTearDown(current.dispose);
    current.beginAuthenticatedSession(user);
    _seedAccountState(current);
    expect(current.beginAuthenticatedSession(user), same(current));
    expect(current.krPortfolioSummary.cash, 987654321);
    expect(current.kisUserAccount, isNotNull);
    expect(current.portfolioLoaded, isTrue);
  });

  for (final fail in [false, true]) {
    test(
        'late previous user activity ${fail ? "error" : "response"} cannot alter admin',
        () async {
      final pending = Completer<List<TradingLogItem>>();
      final api = _SessionApi()..userRuns = pending;
      final regular = DashboardController(api, autoload: false);
      regular.beginAuthenticatedSession(user);
      final oldRequest = regular.loadUserHomeRecentActivity();
      final administrator =
          regular.clearAuthenticatedSession().beginAuthenticatedSession(admin);
      administrator.loading = true;
      administrator.homeRecentActivityError = 'current-session-error';
      addTearDown(regular.dispose);
      addTearDown(administrator.dispose);
      if (fail) {
        pending.completeError(const ApiRequestException('old-session-error'));
      } else {
        pending.complete([_oldRun()]);
      }
      await oldRequest;
      expect(administrator.automationRecentRuns, isEmpty);
      expect(administrator.recentRuns, isEmpty);
      expect(administrator.loading, isTrue);
      expect(administrator.homeRecentActivityError, 'current-session-error');
      expect(regular.automationRecentRuns, isEmpty);
    });
  }
}

void _seedAccountState(DashboardController c) {
  c.krPortfolioSummary =
      PortfolioSummary.fromJson({'currency': 'KRW', 'cash': 987654321});
  c.usPortfolioSummary =
      PortfolioSummary.fromJson({'currency': 'USD', 'cash': 123456});
  c.portfolioLoaded = true;
  c.portfolioLoading = true;
  c.portfolioLoadError = 'old account';
  c.kisUserAccount = UserBrokerAccountSnapshot.fromJson({
    'provider': 'kis',
    'account': {'cash': 987654321}
  });
  c.userBrokerCredentials = const [
    UserBrokerCredential(provider: 'kis', configured: true)
  ];
  c.kisManagedPositions = [
    ManagedPosition.fromJson({'symbol': 'OLD_ACCOUNT'})
  ];
  c.automationRecentRuns = [_oldRun()];
  c.todayAiDecisionsLoaded = true;
  c.todayAiDecisionsRequested = true;
  c.todayAiDecisionsError = 'old AI error';
  c.userTradingSettings = const {'account': 'test01'};
  c.userTradingSettingsLoaded = true;
  c.orderTicketSourceMetadata = const {'owner': 'test01'};
  c.kisTradingSourceContext = const {'owner': 'test01'};
  c.activeAgentConversationKey = 'test01-conversation';
  c.strategyProfileError = 'old strategy';
  c.strategyProfilesLoading = true;
  c.orderValidationLoading = true;
  c.kisLiveConfirmation = true;
}

void _expectCleanSession(DashboardController c) {
  expect(c.krPortfolioSummary.cash, 0);
  expect(c.usPortfolioSummary.cash, 0);
  expect(c.portfolioLoaded, isFalse);
  expect(c.portfolioLoading, isFalse);
  expect(c.portfolioLoadError, isNull);
  expect(c.kisUserAccount, isNull);
  expect(c.alpacaUserAccount, isNull);
  expect(c.userBrokerCredentials, isEmpty);
  expect(c.kisManagedPositions, isEmpty);
  expect(c.automationRecentRuns, isEmpty);
  expect(c.automationRecentOrders, isEmpty);
  expect(c.automationRecentSignals, isEmpty);
  expect(c.recentRuns, isEmpty);
  expect(c.todayAiDecisionsLoaded, isFalse);
  expect(c.todayAiDecisionsRequested, isFalse);
  expect(c.todayAiDecisionsError, isNull);
  expect(c.userTradingSettings, isEmpty);
  expect(c.userHomeAutomationProfiles, isNull);
  expect(c.orderTicketSourceMetadata, isNull);
  expect(c.kisTradingSourceContext, isNull);
  expect(c.activeAgentConversationKey, isNull);
  expect(c.strategyProfiles, isEmpty);
  expect(c.activeStrategyProfile, isNull);
  expect(c.strategyProfileError, isNull);
  expect(c.strategyProfilesLoading, isFalse);
  expect(c.orderValidationLoading, isFalse);
  expect(c.orderValidationResult, isNull);
  expect(c.kisLiveConfirmation, isFalse);
}

TradingLogItem _oldRun() => const TradingLogItem(
      id: 17,
      runKey: 'test01-old-run',
      symbol: 'OLD_ACCOUNT',
      triggerSource: 'scheduler',
      mode: 'entry_scan',
      action: 'hold',
      result: 'hold',
      reason: 'test01',
      relatedOrderId: null,
      createdAt: '2026-10-02T00:50:00Z',
      gateLevel: 2,
    );

class _SessionApi extends ApiClient {
  Completer<List<TradingLogItem>>? userRuns;
  @override
  Future<List<TradingLogItem>> fetchUserTradingRuns({int limit = 20}) =>
      userRuns?.future ?? Future.value([]);
  @override
  Future<AutomationTodayDecisions> fetchUserTodayAiDecisions() async =>
      AutomationTodayDecisions.empty;
}
