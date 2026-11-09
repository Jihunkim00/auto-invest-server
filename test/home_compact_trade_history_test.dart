import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/theme/app_theme.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/home/home_screen.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/portfolio_summary.dart';
import 'package:auto_invest_dashboard/models/trade_fill_history.dart';
import 'package:auto_invest_dashboard/models/user_broker_account_snapshot.dart';

void main() {
  testWidgets('compact LIVE safety and all five desktop metrics share a row',
      (tester) async {
    final controller = _controller(_FakeApi())..settings = _liveSettings;
    await _mount(tester, controller);
    final mode = find.byKey(const ValueKey('home-operation-mode-card'));
    expect(tester.getSize(mode).height, lessThanOrEqualTo(125));
    expect(
        find.descendant(of: mode, matching: find.text('LIVE')), findsOneWidget);
    expect(find.descendant(of: mode, matching: find.text('긴급 정지 ON')),
        findsOneWidget);
    expect(find.descendant(of: mode, matching: find.text('실거래 차단')),
        findsOneWidget);
    expect(find.descendant(of: mode, matching: find.text('실주문 허용 ON')),
        findsOneWidget);
    final card = find.byKey(const ValueKey('home-portfolio-card'));
    final labels = ['총자산', '보유주식 평가액', '예수금', '주문가능', '평가손익'];
    final tops = [
      for (final label in labels)
        tester
            .getTopLeft(find.descendant(of: card, matching: find.text(label)))
            .dy
    ];
    expect(tops.toSet(), hasLength(1));
    expect(tester.takeException(), isNull);
    controller.dispose();
  });

  for (final width in [320.0, 375.0, 600.0]) {
    testWidgets('home cards avoid overflow at width $width and larger text',
        (tester) async {
      final controller = _controller(_FakeApi(), positions: 5)
        ..settings = _liveSettings;
      await _mount(tester, controller, width: width, textScale: 1.3);
      await _show(
          tester, find.byKey(const ValueKey('home-trade-history-card')));
      await tester.tap(find.byKey(const ValueKey('home-trade-history-toggle')));
      await tester.pumpAndSettle();
      await _show(tester,
          find.byKey(const ValueKey('home-latest-ai-decision-card-surface')));
      expect(tester.takeException(), isNull);
      controller.dispose();
    });
  }

  testWidgets(
      'user LIVE safety comes from the user and selected scheduler provider',
      (tester) async {
    final controller = _controller(_FakeApi())
      ..userTradingSettings = {
        'auto_trading_enabled': true,
        'auto_trading_provider': 'alpaca',
        'live_trading_enabled': true,
        'kill_switch': true,
      };
    await _mount(tester, controller);
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.darkTheme,
        home: Scaffold(
            body: HomeScreen(
                controller: controller,
                readOnlyUser: true,
                userTradingMode: 'live'))));
    await tester.pumpAndSettle();
    final mode = find.byKey(const ValueKey('home-operation-mode-card'));
    expect(
        find.descendant(of: mode, matching: find.text('LIVE')), findsOneWidget);
    expect(find.descendant(of: mode, matching: find.text('긴급 정지 ON')),
        findsOneWidget);
    expect(find.descendant(of: mode, matching: find.text('긴급 정지 ON · 실거래 차단')),
        findsOneWidget);
    expect(find.descendant(of: mode, matching: find.text('KIS 스케줄러 OFF')),
        findsOneWidget);
    controller.dispose();
  });

  for (final count in [0, 1, 5]) {
    testWidgets('positions $count are compact and additional positions expand',
        (tester) async {
      final controller = _controller(_FakeApi(), positions: count);
      await _mount(tester, controller);
      final card = find.byKey(const ValueKey('home-positions-card'));
      if (count == 0) {
        expect(tester.getSize(card).height, lessThan(105));
      } else {
        expect(find.text('가짜종목0 (FAKE0)'), findsOneWidget);
      }
      if (count > 3) {
        expect(find.text('가짜종목4 (FAKE4)'), findsNothing);
        await tester.tap(find.byKey(const ValueKey('home-positions-toggle')));
        await tester.pumpAndSettle();
        expect(find.text('가짜종목4 (FAKE4)'), findsOneWidget);
        await tester.tap(find.byKey(const ValueKey('home-positions-toggle')));
        await tester.pumpAndSettle();
        expect(find.text('가짜종목4 (FAKE4)'), findsNothing);
      }
      controller.dispose();
    });
  }

  testWidgets(
      'history starts collapsed, expands, filters on server and loads more',
      (tester) async {
    final api = _FakeApi();
    final controller = _controller(api);
    await _mount(tester, controller);
    expect(find.byKey(const ValueKey('trade-period-today')), findsNothing);
    expect(find.textContaining('오늘 25건'), findsOneWidget);
    expect(find.byKey(const ValueKey('trade-fill-kis:1')), findsOneWidget);
    expect(find.byKey(const ValueKey('trade-fill-kis:3')), findsNothing);
    // The compact preview itself is part of the card's expansion target.
    await tester.tap(find.byKey(const ValueKey('trade-fill-kis:1')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('trade-fill-kis:3')), findsOneWidget);
    expect(find.textContaining('2026-11-09 10:01:00 KST'), findsWidgets);
    expect(find.textContaining('부분 체결'), findsWidgets);
    for (final period in ['week', 'month', 'year', 'today']) {
      await tester.tap(find.byKey(ValueKey('trade-period-$period')));
      await tester.pumpAndSettle();
      expect(api.calls.last['period'], period);
    }
    final more = find.byKey(const ValueKey('trade-history-more'));
    await _show(tester, more);
    await tester.tap(more);
    await tester.pumpAndSettle();
    expect(api.calls.last['offset'], 20);
    expect(api.calls.last['asOf'], '2026-11-09T15:00:00+09:00');
    expect(controller.tradeFills, hasLength(4));
    // A repeated fill returned at a page boundary is rendered once.
    expect(controller.tradeFills.map((fill) => fill.id).toSet(), hasLength(4));
    await _show(
        tester, find.byKey(const ValueKey('home-trade-history-toggle')));
    await tester.tap(find.byKey(const ValueKey('home-trade-history-toggle')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('trade-period-today')), findsNothing);
    expect(api.calls, hasLength(6));
    controller.dispose();
  });

  testWidgets('history error and retry stay separate from portfolio and AI',
      (tester) async {
    final api = _FakeApi()..fail = true;
    final controller = _controller(api);
    await _mount(tester, controller);
    expect(find.byKey(const ValueKey('trade-history-retry')), findsOneWidget);
    expect(find.textContaining('선택한 기간에 체결된 거래가 없습니다.'), findsNothing);
    expect(find.byKey(const ValueKey('home-portfolio-card')), findsOneWidget);
    expect(find.byKey(const ValueKey('home-latest-ai-decision-card-surface')),
        findsOneWidget);
    api.fail = false;
    await tester.tap(find.byKey(const ValueKey('trade-history-retry')));
    await tester.pumpAndSettle();
    expect(find.textContaining('오늘 25건'), findsOneWidget);
    expect(find.byKey(const ValueKey('trade-history-retry')), findsNothing);
    controller.dispose();
  });

  testWidgets('history loading and empty states and pull to refresh',
      (tester) async {
    final response = Completer<TradeFillPage>();
    final api = _FakeApi()..pending = response;
    final controller = _controller(api);
    await _mount(tester, controller, settle: false);
    expect(find.byKey(const ValueKey('trade-history-loading')), findsOneWidget);
    expect(find.textContaining('선택한 기간에 체결된 거래가 없습니다.'), findsNothing);
    response.complete(_page(empty: true));
    api.pending = null;
    await tester.pumpAndSettle();
    expect(find.text('오늘 체결 0건'), findsOneWidget);
    final refresh =
        tester.widget<RefreshIndicator>(find.byType(RefreshIndicator));
    // User refresh avoids administrator startup requests in this isolated UI.
    await tester.pumpWidget(MaterialApp(
        theme: AppTheme.darkTheme,
        home: Scaffold(
            body: HomeScreen(controller: controller, readOnlyUser: true))));
    final userRefresh =
        tester.widget<RefreshIndicator>(find.byType(RefreshIndicator));
    expect(refresh.onRefresh, isNotNull);
    await userRefresh.onRefresh();
    await tester.pumpAndSettle();
    expect(api.calls, hasLength(2));
    expect(find.textContaining('오늘 25건'), findsOneWidget);
    controller.dispose();
  });

  testWidgets(
      'broker history emphasizes title count totals and one recent trade',
      (tester) async {
    final api = _FakeApi();
    final controller = _controller(api);
    await _mount(tester, controller);
    final title = tester.widget<Text>(find.text('거래 내역'));
    final count =
        tester.widget<Text>(find.byKey(const ValueKey('trade-history-count')));
    final amount = tester
        .widget<Text>(find.byKey(const ValueKey('trade-history-buy-total')));
    expect(title.style!.fontWeight!.value,
        greaterThanOrEqualTo(FontWeight.bold.value));
    expect(count.style!.fontSize, greaterThanOrEqualTo(20));
    expect(count.style!.fontWeight, FontWeight.w900);
    expect(amount.style!.fontWeight, FontWeight.w800);
    expect(amount.style!.color, AppTheme.danger);
    expect(find.byKey(const ValueKey('trade-fill-kis:1')), findsOneWidget);
    expect(find.byKey(const ValueKey('trade-fill-kis:2')), findsNothing);
    expect(api.calls.single['period'], 'today');
    await tester.tap(find.byKey(const ValueKey('trade-history-refresh')));
    await tester.pumpAndSettle();
    expect(api.calls, hasLength(2));
    await tester.tap(find.byKey(const ValueKey('trade-history-expand')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('trade-fill-kis:2')), findsOneWidget);
    expect(find.text('한국투자증권 계좌 체결 · KST'), findsOneWidget);
    final chip = tester
        .widget<ChoiceChip>(find.byKey(const ValueKey('trade-period-today')));
    expect(chip.selectedColor, AppTheme.primaryAccent);
    expect(
        tester
            .getSize(find.byKey(const ValueKey('home-operation-mode-card')))
            .height,
        lessThanOrEqualTo(125));
    controller.dispose();
  });

  for (final entry in {
    'not_connected': '한국투자증권 계좌 연결이 필요합니다.',
    'authentication_failed': '한국투자증권 인증을 확인해 주세요.',
    'error': '거래 내역을 불러오지 못했습니다.',
    'incomplete': '일부 거래 내역을 확인하지 못했습니다.',
  }.entries) {
    testWidgets('broker ${entry.key} is distinct from successful zero trades',
        (tester) async {
      final api = _FakeApi()..brokerStatus = entry.key;
      final controller = _controller(api);
      await _mount(tester, controller);
      expect(find.text(entry.value), findsOneWidget);
      expect(find.textContaining('체결 0건'), findsNothing);
      expect(find.text('매수 ₩0'), findsNothing);
      expect(find.byKey(const ValueKey('home-portfolio-card')), findsOneWidget);
      expect(find.byKey(const ValueKey('home-latest-ai-decision-card-surface')),
          findsOneWidget);
      controller.dispose();
    });
  }

  test('regular user KIS GET targets only the authenticated user endpoint',
      () async {
    final api = ApiClient(client: MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/users/me/trading/executions');
      expect(request.url.queryParameters['period'], 'day');
      expect(request.url.queryParameters.containsKey('user_id'), isFalse);
      expect(request.url.queryParameters.containsKey('CANO'), isFalse);
      return http.Response(jsonEncode(_payload()), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    await api.fetchTradeFills(provider: 'kis', userScoped: true);
  });

  test('malformed broker success cannot masquerade as zero', () {
    expect(() => TradeFillPage.fromJson({..._payload(), 'count': null}),
        throwsFormatException);
    expect(() => TradeFillPage.fromJson({..._payload(), 'complete': false}),
        throwsFormatException);
  });

  test('late responses never restore previous broker or account data',
      () async {
    final api = _FakeApi();
    final controller = _controller(api);
    final oldRequest = Completer<TradeFillPage>();
    api.pending = oldRequest;
    final first = controller.loadTradeFills();
    controller.setProvider(SelectedProvider.alpaca);
    expect(controller.tradeFills, isEmpty);
    api.pending = null;
    await controller.loadTradeFills();
    oldRequest.complete(_page());
    await first;
    expect(
        controller.tradeFills.every((fill) => fill.currency == 'USD'), isTrue);
    controller.beginAuthenticatedSession(const AuthUser(
        id: 1,
        username: 'admin',
        role: 'admin',
        enabled: true,
        setupCompleted: true));
    final next = controller.beginAuthenticatedSession(const AuthUser(
        id: 17,
        username: 'test01',
        role: 'user',
        enabled: true,
        setupCompleted: true));
    expect(controller.tradeFills, isEmpty);
    expect(next.tradeFills, isEmpty);
    next.dispose();
    controller.dispose();
  });

  test('API uses GET with period, offset and snapshot boundary only', () async {
    final api = ApiClient(client: MockClient((request) async {
      expect(request.method, 'GET');
      expect(request.url.path, '/kis/account/executions');
      expect(Map.of(request.url.queryParameters)..remove('_ts'), {
        'period': 'year',
        'limit': '20',
        'offset': '20',
        'as_of': '2026-11-09T15:00:00+09:00',
      });
      return http.Response(jsonEncode(_payload()), 200,
          headers: {'content-type': 'application/json; charset=utf-8'});
    }));
    await api.fetchTradeFills(
        provider: 'kis',
        period: 'year',
        offset: 20,
        asOf: '2026-11-09T15:00:00+09:00');
  });

  test(
      'older period and retired login requests cannot overwrite the current list',
      () async {
    final api = _FakeApi();
    final controller = _controller(api);
    final oldPeriod = Completer<TradeFillPage>();
    api.pending = oldPeriod;
    final first = controller.loadTradeFills();
    api.pending = null;
    await controller.loadTradeFills(period: 'year');
    oldPeriod.complete(_page(empty: true));
    await first;
    expect(controller.tradeFillPeriod, 'year');
    expect(controller.tradeFills, isNotEmpty);

    controller.beginAuthenticatedSession(const AuthUser(
        id: 1,
        username: 'admin',
        role: 'admin',
        enabled: true,
        setupCompleted: true));
    final oldAccount = Completer<TradeFillPage>();
    api.pending = oldAccount;
    final oldRead = controller.loadTradeFills(force: true);
    final next = controller.beginAuthenticatedSession(const AuthUser(
        id: 17,
        username: 'test01',
        role: 'user',
        enabled: true,
        setupCompleted: true));
    api.pending = null;
    await next.loadTradeFills();
    oldAccount.complete(_page(empty: true));
    await oldRead;
    expect(controller.tradeFills, isEmpty);
    expect(next.tradeFills, isNotEmpty);
    controller.dispose();
    next.dispose();
  });

  test('missing portfolio amounts remain unknown for user snapshots and JSON',
      () {
    final summary = PortfolioSummary.fromUserBrokerAccount(
        UserBrokerAccountSnapshot.fromJson({
      'provider': 'kis',
      'connected': true,
      'account': {'currency': 'KRW'},
      'positions': [
        {'symbol': 'FAKE', 'quantity': 1}
      ],
    }));
    expect(summary.cashKnown, isFalse);
    expect(summary.marketValueKnown, isFalse);
    expect(summary.unrealizedPlKnown, isFalse);
    expect(summary.positions.single.unrealizedPlKnown, isFalse);
    expect(PortfolioSummary.fromJson({}).unrealizedPlKnown, isFalse);
  });
}

Future<void> _mount(WidgetTester tester, DashboardController controller,
    {double width = 1280, double textScale = 1, bool settle = true}) async {
  tester.view.devicePixelRatio = 1;
  tester.view.physicalSize = Size(width, 1600);
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
  await tester.pumpWidget(MaterialApp(
    theme: AppTheme.darkTheme,
    home: MediaQuery(
        data: MediaQueryData(
            size: Size(width, 1600), textScaler: TextScaler.linear(textScale)),
        child: Scaffold(body: HomeScreen(controller: controller))),
  ));
  await tester.pump();
  if (settle) await tester.pumpAndSettle();
}

Future<void> _show(WidgetTester tester, Finder finder) async {
  await tester.dragUntilVisible(
      finder,
      find.byKey(const ValueKey('home-simple-scroll-view')),
      const Offset(0, -300),
      maxIteration: 25);
  await tester.ensureVisible(finder);
  await tester.pumpAndSettle();
}

DashboardController _controller(_FakeApi api, {int positions = 0}) =>
    DashboardController(api, autoload: false)
      ..portfolioLoaded = true
      ..krPortfolioSummary = PortfolioSummary.fromJson({
        'currency': 'KRW',
        'total_market_value': 123456,
        'total_unrealized_pl': -123,
        'cash': 200000,
        'orderable_cash': 150000,
        'positions': [
          for (var i = 0; i < positions; i++)
            {
              'symbol': 'FAKE$i',
              'name': '가짜종목$i',
              'qty': 2,
              'unrealized_pl': i.isEven ? 123 : -123,
            }
        ],
      });

const _liveSettings = OpsSettings(
    schedulerEnabled: true,
    botEnabled: true,
    dryRun: false,
    killSwitch: true,
    brokerMode: 'Live',
    defaultGateLevel: 2,
    maxDailyTrades: 5,
    maxDailyEntries: 2,
    minEntryScore: 65,
    minScoreGap: 3,
    currentOperationMode: 'full_live_test_mode',
    kisSchedulerAllowRealOrders: true);

Map<String, dynamic> _payload(
        {bool empty = false, bool more = false, String provider = 'kis'}) =>
    {
      'environment': 'live',
      'end_at': '2026-11-09T15:00:00+09:00',
      'source': 'kis_broker_executions',
      'status': 'success',
      'complete': true,
      'count': empty ? 0 : 25,
      'total_buy_amount': empty ? 0 : 30000,
      'total_sell_amount': empty ? 0 : 15000,
      'unknown_amount_count': 0,
      'next_offset': empty || more ? null : 20,
      'items': [
        if (!empty)
          for (final i in more ? [3, 4] : [1, 2, 3])
            {
              'id': '$provider:$i',
              'symbol': 'FAKE$i',
              'name': '가짜종목$i',
              'side': i.isEven ? 'sell' : 'buy',
              'filled_qty': 2,
              'avg_fill_price': 15000,
              'filled_amount': 30000,
              'currency': provider == 'kis' ? 'KRW' : 'USD',
              'partial': i == 1,
              'trade_date': '2026-11-09',
              'executed_at': '2026-11-09T01:01:00Z',
            }
      ],
    };

TradeFillPage _page(
        {bool empty = false, bool more = false, String provider = 'kis'}) =>
    TradeFillPage.fromJson(
        _payload(empty: empty, more: more, provider: provider));

class _FakeApi extends ApiClient {
  _FakeApi() : super(client: MockClient((_) async => http.Response('{}', 503)));
  bool fail = false;
  String? brokerStatus;
  Completer<TradeFillPage>? pending;
  final calls = <Map<String, Object?>>[];

  @override
  Future<TradeFillPage> fetchTradeFills(
      {required String provider,
      bool userScoped = false,
      String period = 'today',
      int offset = 0,
      String? asOf}) async {
    calls.add({
      'provider': provider,
      'period': period,
      'offset': offset,
      'asOf': asOf
    });
    if (fail) throw const ApiRequestException('fake failure');
    if (brokerStatus != null) {
      return TradeFillPage.fromJson({
        ..._payload(empty: true),
        'status': brokerStatus,
        'complete': false,
        'count': null,
        'total_buy_amount': null,
        'total_sell_amount': null
      });
    }
    if (pending != null) return pending!.future;
    return _page(more: offset > 0, provider: provider);
  }
}
