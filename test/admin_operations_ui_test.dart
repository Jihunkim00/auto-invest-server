import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/admin/admin_operation_screens.dart';
import 'package:auto_invest_dashboard/features/admin/admin_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/order_ticket_section.dart';
import 'package:auto_invest_dashboard/models/auth_session.dart';

void main() {
  testWidgets(
      'compact admin menu separates analysis, buy, sell and retains operations',
      (tester) async {
    tester.view.physicalSize = const Size(360, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await tester
        .pumpWidget(MaterialApp(home: AdminScreen(controller: controller)));
    for (final title in [
      '단일 종목 분석',
      '단일 종목 매수',
      '단일 종목 매도',
      '보유 종목 / 계좌 조회',
      '주문 내역 / 체결 조회',
      '운영 로그 / 진단',
      'Watchlist 분석',
      '위험관리 / 운영 설정',
      '관리자 계정 관리'
    ]) {
      await tester.scrollUntilVisible(find.text(title), 250,
          scrollable: find.byType(Scrollable).last);
      expect(find.text(title), findsOneWidget);
      expect(tester.takeException(), isNull);
    }
    expect(find.byKey(const ValueKey('admin-open-test4')), findsNothing);
    await tester.scrollUntilVisible(
        find.byKey(const ValueKey('admin-advanced-tools')), 250,
        scrollable: find.byType(Scrollable).last);
    await tester.tap(find.byKey(const ValueKey('admin-advanced-tools')));
    await tester.pumpAndSettle();
    expect(find.text('KIS 자동매매 운영 상태'), findsOneWidget);
    expect(find.text('후보 분석 상세'), findsOneWidget);
    expect(backend.requests, isEmpty);
  });

  testWidgets(
      'analysis sends only safe request and never changes the existing order draft',
      (tester) async {
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false)
      ..orderTicketSymbol = '000660'
      ..orderTicketQtyInput = '9'
      ..orderTicketSide = 'sell'
      ..kisLiveConfirmation = true
      ..kisGuardedRunConfirmation = true;
    addTearDown(controller.dispose);
    await _analysis(tester, controller);
    expect(backend.requests, isEmpty);
    final button = find.byKey(const ValueKey('admin-analysis-run'));
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    await tester.enterText(
        find.byKey(const ValueKey('admin-analysis-symbol')), '00593');
    await tester.pump();
    expect(tester.widget<FilledButton>(button).onPressed, isNull);
    await tester.enterText(
        find.byKey(const ValueKey('admin-analysis-symbol')), '005930');
    await tester.pump();
    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(backend.requests.map((r) => r.url.path), ['/kis/trading/run-once']);
    final body =
        jsonDecode(backend.requests.single.body) as Map<String, dynamic>;
    expect(body['symbol'], '005930');
    expect(body['requested_action'], 'analyze_only');
    expect(body['confirm_live'], isFalse);
    expect(body['dry_run'], isTrue);
    expect(body.containsKey('quantity'), isFalse);
    expect(body.containsKey('amount'), isFalse);
    expect(body['gate_level'], controller.selectedGateLevel);
    expect(find.byType(OrderTicketSection), findsNothing);
    expect(find.text('단일 종목 분석'), findsOneWidget);
    expect(controller.orderTicketSymbol, '000660');
    expect(controller.orderTicketQtyInput, '9');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.kisLiveConfirmation, isTrue);
    expect(controller.latestKisSingleSymbolTradingResult, isNull);
    expect(find.byKey(const ValueKey('admin-analysis-summary')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('analysis loading rejects duplicate clicks and disposal is safe',
      (tester) async {
    final backend = _MockBackend()
      ..analysisPending = Completer<http.Response>();
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await _analysis(tester, controller);
    await tester.enterText(
        find.byKey(const ValueKey('admin-analysis-symbol')), '005930');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('admin-analysis-run')));
    await tester.pump();
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const ValueKey('admin-analysis-run')))
            .onPressed,
        isNull);
    expect(backend.requests, hasLength(1));
    await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    backend.analysisPending!
        .complete(_json({'result': 'skipped', 'reason': 'analysis_only'}));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    expect(backend.requests, hasLength(1));
  });

  testWidgets('analysis errors allow retry and do not submit orders',
      (tester) async {
    final backend = _MockBackend()..analysisFails = true;
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await _analysis(tester, controller);
    await tester.enterText(
        find.byKey(const ValueKey('admin-analysis-symbol')), '005930');
    await tester.pump();
    await tester.tap(find.byKey(const ValueKey('admin-analysis-run')));
    await tester.pumpAndSettle();
    expect(find.textContaining('analysis failed'), findsOneWidget);
    backend.analysisFails = false;
    await tester.tap(find.byKey(const ValueKey('admin-analysis-run')));
    await tester.pumpAndSettle();
    expect(backend.requests, hasLength(2));
    expect(backend.requests.every((r) => r.url.path == '/kis/trading/run-once'),
        isTrue);
  });

  testWidgets(
      'KIS-only tools preserve selected Alpaca broker and disable analysis',
      (tester) async {
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false)
      ..selectedProvider = SelectedProvider.alpaca;
    addTearDown(controller.dispose);
    await _analysis(tester, controller);
    expect(controller.selectedProvider, SelectedProvider.alpaca);
    expect(
        tester
            .widget<TextField>(
                find.byKey(const ValueKey('admin-analysis-symbol')))
            .enabled,
        isFalse);
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const ValueKey('admin-analysis-run')))
            .onPressed,
        isNull);
    expect(backend.requests, isEmpty);
  });

  for (final side in ['buy', 'sell']) {
    testWidgets(
        'admin $side requires validation, checkbox and final confirmation',
        (tester) async {
      _largeView(tester);
      final backend = _MockBackend();
      final controller = DashboardController(backend.api, autoload: false)
        ..kisLiveConfirmation = true;
      addTearDown(controller.dispose);
      await tester
          .pumpWidget(MaterialApp(home: AdminScreen(controller: controller)));
      await tester.tap(find.byKey(ValueKey(side == 'buy'
          ? 'admin-open-manual-trading'
          : 'admin-open-manual-sell')));
      await tester.pumpAndSettle();
      expect(controller.orderTicketSide, side);
      expect(controller.kisLiveConfirmation, isFalse);
      expect(backend.requests, isEmpty);
      final submit = find
          .text(side == 'buy' ? 'Submit Live KIS Order' : 'Submit Manual Sell');
      await tester.ensureVisible(submit);
      await tester.tap(submit);
      await tester.pumpAndSettle();
      expect(
          find.text('Confirm KIS Live ${side.toUpperCase()}'), findsOneWidget);
      expect(backend.at('/kis/orders/validate'), hasLength(1));
      expect(backend.at('/kis/orders/manual-submit'), isEmpty);
      expect(
          tester
              .widget<FilledButton>(
                  find.byKey(const Key('kis_live_order_dialog_submit_button')))
              .onPressed,
          isNull);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
      await tester.ensureVisible(find.byType(CheckboxListTile));
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pumpAndSettle();
      await tester.ensureVisible(submit);
      await tester.tap(submit);
      await tester.pumpAndSettle();
      expect(backend.at('/kis/orders/manual-submit'), isEmpty);
      await tester
          .tap(find.byKey(const Key('kis_live_order_dialog_submit_button')));
      await tester.pumpAndSettle();
      final submitted = backend.at('/kis/orders/manual-submit');
      expect(submitted, hasLength(1));
      expect((jsonDecode(submitted.single.body) as Map)['side'], side);
      expect(
          (jsonDecode(submitted.single.body) as Map)['confirm_live'], isTrue);
      await tester.pumpWidget(const SizedBox.shrink());
      expect(tester.takeException(), isNull);
    });

    testWidgets(
        'entry cutoff blocks admin buy and allows validated admin sell: $side',
        (tester) async {
      _largeView(tester);
      final backend = _MockBackend()..entryAllowed = false;
      final controller = DashboardController(backend.api, autoload: false)
        ..orderTicketSide = side;
      addTearDown(controller.dispose);
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: AdminOperationScreen(
                  controller: controller,
                  operation: AdminOperation.manualOrder))));
      await tester.tap(find.byType(CheckboxListTile));
      await tester.pumpAndSettle();
      final submit = find
          .text(side == 'buy' ? 'Submit Live KIS Order' : 'Submit Manual Sell');
      await tester.ensureVisible(submit);
      await tester.tap(submit);
      await tester.pumpAndSettle();
      expect(
          tester
                  .widget<FilledButton>(find
                      .byKey(const Key('kis_live_order_dialog_submit_button')))
                  .onPressed !=
              null,
          side == 'sell');
      expect(backend.at('/kis/orders/manual-submit'), isEmpty);
      await tester.tap(find.text('Cancel'));
      await tester.pumpAndSettle();
    });
  }

  testWidgets('rejected validation keeps final live submit disabled',
      (tester) async {
    _largeView(tester);
    final backend = _MockBackend()..validationAllowed = false;
    final controller = DashboardController(backend.api, autoload: false)
      ..kisLiveConfirmation = true;
    addTearDown(controller.dispose);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AdminOperationScreen(
                controller: controller,
                operation: AdminOperation.manualOrder))));
    await tester.ensureVisible(find.text('Submit Live KIS Order'));
    await tester.tap(find.text('Submit Live KIS Order'));
    await tester.pumpAndSettle();
    expect(find.textContaining('insufficient_cash'), findsWidgets);
    expect(
        tester
            .widget<FilledButton>(
                find.byKey(const Key('kis_live_order_dialog_submit_button')))
            .onPressed,
        isNull);
    expect(backend.at('/kis/orders/manual-submit'), isEmpty);
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
  });

  testWidgets(
      'sell preparation uses existing endpoint and never validates or submits',
      (tester) async {
    _largeView(tester);
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false)
      ..orderTicketSide = 'sell'
      ..kisLiveConfirmation = true;
    addTearDown(controller.dispose);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AdminOperationScreen(
                controller: controller,
                operation: AdminOperation.manualOrder))));
    await tester.tap(find.byKey(const ValueKey('admin-prepare-sell')));
    await tester.pumpAndSettle();
    expect(
        backend.at('/kis/positions/005930/prepare-manual-sell'), hasLength(1));
    expect(controller.orderTicketQtyInput, '2');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.kisLiveConfirmation, isFalse);
    expect(backend.at('/kis/orders/validate'), isEmpty);
    expect(backend.at('/kis/orders/manual-submit'), isEmpty);
  });

  testWidgets(
      'account refresh reads existing KIS endpoints without order submission',
      (tester) async {
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AdminOperationScreen(
                controller: controller, operation: AdminOperation.account))));
    expect(backend.requests, isEmpty);
    await tester.tap(find.text(
        '\uACC4\uC88C / \uBCF4\uC720 \uC885\uBAA9 \uC0C8\uB85C\uACE0\uCE68'));
    await tester.pumpAndSettle();
    expect(backend.at('/kis/account/balance'), hasLength(1));
    expect(backend.at('/kis/account/positions'), hasLength(1));
    expect(controller.krPortfolioSummary.cash, 3000000);
    expect(controller.krPortfolioSummary.orderableCash, 2000000);
    expect(controller.krPortfolioSummary.positions.single.symbol, '005930');
    expect(controller.krPortfolioSummary.positions.single.qty, 2);
    expect(find.byType(OrderTicketSection), findsNothing);
    expect(backend.at('/kis/orders/manual-submit'), isEmpty);
  });

  testWidgets(
      'order history refresh and sync use existing endpoints without a submit ticket',
      (tester) async {
    _largeView(tester);
    final backend = _MockBackend()..hasOrder = true;
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: AdminOperationScreen(
                controller: controller, operation: AdminOperation.orders))));
    expect(backend.requests, isEmpty);
    await tester.tap(find.byKey(const ValueKey('admin-orders-refresh')));
    await tester.pumpAndSettle();
    expect(backend.at('/kis/orders'), hasLength(1));
    expect(find.text('0001234567'), findsOneWidget);
    expect(controller.kisOrders.single.orderId, 42);
    await tester.tap(find.text('Sync Status'));
    await tester.pumpAndSettle();
    expect(backend.at('/kis/orders/42/sync'), hasLength(1));
    expect(controller.selectedKisOrder!.internalStatus, 'FILLED');
    expect(find.byType(OrderTicketSection), findsNothing);
    expect(backend.at('/kis/orders/manual-submit'), isEmpty);
    expect(tester.takeException(), isNull);
  });

  testWidgets('account management remains accessible via its own screen',
      (tester) async {
    _largeView(tester);
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await tester
        .pumpWidget(MaterialApp(home: AdminScreen(controller: controller)));
    await tester.tap(find.byKey(const ValueKey('admin-open-accounts')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('admin-user-management')), findsOneWidget);
    expect(find.text('test01'), findsOneWidget);
    expect(backend.at('/admin/users'), hasLength(1));
    await tester.pageBack();
    await tester.pumpAndSettle();
    expect(find.text('관리자 도구'), findsOneWidget);
  });

  testWidgets('regular user cannot mount admin tools or issue admin requests',
      (tester) async {
    final backend = _MockBackend();
    final controller = DashboardController(backend.api, autoload: false);
    addTearDown(controller.dispose);
    await controller.bootstrapRegularUserHome(const AuthUser(
        id: 2,
        username: 'test01',
        role: 'user',
        enabled: true,
        setupCompleted: true));
    backend.requests.clear();
    await tester
        .pumpWidget(MaterialApp(home: AdminScreen(controller: controller)));
    await tester.pumpAndSettle();
    expect(find.text('관리자 권한이 필요합니다.'), findsOneWidget);
    expect(find.byKey(const ValueKey('admin-open-analysis')), findsNothing);
    expect(find.byKey(const ValueKey('admin-open-accounts')), findsNothing);
    expect(backend.requests, isEmpty);
    await _analysis(tester, controller);
    expect(find.byKey(const ValueKey('admin-analysis-run')), findsNothing);
    for (final operation in AdminOperation.values) {
      await tester.pumpWidget(MaterialApp(
          home: Scaffold(
              body: AdminOperationScreen(
                  controller: controller, operation: operation))));
      await tester.pumpAndSettle();
      expect(find.text('관리자 권한이 필요합니다.'), findsOneWidget);
    }
    expect(backend.requests, isEmpty);
  });
}

Future<void> _analysis(
    WidgetTester tester, DashboardController controller) async {
  await tester.pumpWidget(MaterialApp(
      home: Scaffold(
          body: AdminSingleSymbolAnalysisScreen(controller: controller))));
  await tester.pumpAndSettle();
}

void _largeView(WidgetTester tester) {
  tester.view.physicalSize = const Size(1400, 2600);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

http.Response _json(Map<String, dynamic> body, [int status = 200]) =>
    http.Response(jsonEncode(body), status,
        headers: {'content-type': 'application/json; charset=utf-8'});

class _MockBackend {
  late final api = ApiClient(client: MockClient(_handle));
  final requests = <http.Request>[];
  Completer<http.Response>? analysisPending;
  bool analysisFails = false;
  bool hasOrder = false;
  bool orderSynced = false;
  bool validationAllowed = true;
  bool entryAllowed = true;
  List<http.Request> at(String path) =>
      requests.where((r) => r.url.path == path).toList();

  Future<http.Response> _handle(http.Request request) async {
    requests.add(request);
    final path = request.url.path;
    final body = request.body.isEmpty
        ? <String, dynamic>{}
        : jsonDecode(request.body) as Map<String, dynamic>;
    if (path == '/kis/trading/run-once') {
      if (analysisPending != null) return analysisPending!.future;
      if (analysisFails) return _json({'detail': 'analysis failed'}, 500);
      return _json({
        'result': 'skipped',
        'action': 'buy',
        'reason': 'analysis_only',
        'requested_symbol': body['symbol'],
        'analyzed_symbol': body['symbol'],
        'symbol_match': true,
        'current_price': 70000,
        'final_buy_score': 88,
        'quant_buy_score': 80,
        'gpt_buy_score': 86,
        'effective_min_entry_score': 65,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false
      });
    }
    if (path == '/kis/manual-order/status') return _json(_safety);
    if (path == '/kis/orders/validate') {
      return _json({
        ..._safety,
        ...body,
        'provider': 'kis',
        'market': 'KR',
        'dry_run': true,
        'validated_for_submission': validationAllowed,
        'can_submit_later': validationAllowed,
        'submit_allowed': validationAllowed,
        'current_price': 70000,
        'available_cash': 3000000,
        'held_qty': 2,
        'block_reasons': validationAllowed ? [] : ['insufficient_cash'],
        'validated_at': DateTime.now().toUtc().toIso8601String(),
        'validation_expires_at': DateTime.now()
            .toUtc()
            .add(const Duration(minutes: 2))
            .toIso8601String()
      });
    }
    if (path == '/kis/orders/manual-submit') {
      return _json({
        'order_id': 42,
        'symbol': body['symbol'],
        'side': body['side'],
        'requested_qty': body['qty'],
        'filled_qty': body['qty'],
        'remaining_qty': 0,
        'internal_status': 'FILLED',
        'broker_order_status': 'filled',
        'is_terminal': true,
        'real_order_submitted': true
      });
    }
    if (path == '/kis/orders') {
      return _json({
        'orders': hasOrder ? [_order] : []
      });
    }
    if (path == '/kis/orders/42/sync') {
      orderSynced = true;
      return _json(_order);
    }
    if (path == '/kis/account/balance') {
      return _json({'cash': 3000000, 'orderable_cash': 2000000});
    }
    if (path == '/kis/account/positions') {
      return _json({
        'positions': [
          {
            'symbol': '005930',
            'qty': 2,
            'market_value': 140000,
            'cost_basis': 130000
          }
        ]
      });
    }
    if (path == '/kis/positions/005930/prepare-manual-sell') {
      return _json({
        'symbol': '005930',
        'quantity': 2,
        'can_prepare': true,
        'company_name': 'Samsung Electronics',
        'current_price': 70000,
        'estimated_amount': 140000
      });
    }
    if (path == '/admin/users') {
      return _json({
        'users': [
          {
            'id': 2,
            'username': 'test01',
            'role': 'user',
            'enabled': true,
            'setup_completed': true
          }
        ]
      });
    }
    return _json({});
  }

  Map<String, dynamic> get _order => {
        'order_id': 42,
        'symbol': '005930',
        'side': 'buy',
        'requested_qty': 2,
        'filled_qty': orderSynced ? 2 : 0,
        'remaining_qty': orderSynced ? 0 : 2,
        'internal_status': orderSynced ? 'FILLED' : 'SUBMITTED',
        'is_terminal': orderSynced,
        'kis_odno': '0001234567'
      };

  Map<String, dynamic> get _safety => {
        'runtime_dry_run': false,
        'kill_switch': false,
        'kis_enabled': true,
        'kis_real_order_enabled': true,
        'market_open': true,
        'entry_allowed_now': entryAllowed,
        'no_new_entry_after': '15:00'
      };
}
