import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_shadow_exit_review_queue.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';

void main() {
  test('fetchKisShadowExitReviewQueue calls GET review-queue endpoint',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_queueJson()), 200);
      }),
    );

    final result =
        await client.fetchKisShadowExitReviewQueue(days: 14, limit: 7);

    expect(captured.method, 'GET');
    expect(captured.url.path, '/kis/exit-shadow/review-queue');
    expect(captured.url.queryParameters['days'], '14');
    expect(captured.url.queryParameters['limit'], '7');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(result.mode, 'shadow_exit_review_queue');
  });

  test('mark and dismiss call queue state endpoints only', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_actionJson()), 200);
      }),
    );

    await client.markKisShadowExitQueueItemReviewed(
      '005930:take_profit:cost_basis_pl_pct',
      note: 'reviewed',
    );
    await client.dismissKisShadowExitQueueItem(
      '005930:take_profit:cost_basis_pl_pct',
      note: 'dismissed',
    );

    expect(requests.first.method, 'POST');
    expect(requests.first.url.path,
        '/kis/exit-shadow/review-queue/005930%3Atake_profit%3Acost_basis_pl_pct/mark-reviewed');
    expect(requests.first.body, contains('operator_note'));
    expect(requests.last.url.path,
        '/kis/exit-shadow/review-queue/005930%3Atake_profit%3Acost_basis_pl_pct/dismiss');
    expect(requests.join('\n'), isNot(contains('/kis/orders/manual-submit')));
    expect(requests.join('\n'), isNot(contains('/kis/orders/validate')));
  });

  testWidgets('queue card shows operator review labels and summary',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeQueueApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('KIS Shadow Exit Review Queue'), findsOneWidget);
    expect(find.text('OPERATOR REVIEW'), findsOneWidget);
    expect(find.text('SHADOW EXIT ALERTS'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('NO MANUAL SUBMIT'), findsWidgets);
    expect(find.text('LIVE AUTO SELL DISABLED'), findsWidgets);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsWidgets);
    expect(find.text('Refresh Queue'), findsOneWidget);
    expect(find.text('Enable Auto Sell'), findsNothing);
    expect(find.text('Enable Scheduler Real Orders'), findsNothing);
    expect(find.text('Auto Sell'), findsNothing);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    await tester.ensureVisible(find.text('Refresh Queue'));
    await tester.tap(find.text('Refresh Queue'));
    await tester.pumpAndSettle();

    expect(api.fetchQueueCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.text('open count'.toUpperCase()), findsOneWidget);
    expect(find.text('reviewed count'.toUpperCase()), findsOneWidget);
    expect(find.text('dismissed count'.toUpperCase()), findsOneWidget);
    expect(find.text('would-sell open'.toUpperCase()), findsOneWidget);
    expect(find.text('manual-review open'.toUpperCase()), findsOneWidget);
    expect(find.text('repeated symbols'.toUpperCase()), findsOneWidget);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('take_profit'), findsOneWidget);
    expect(find.text('3'), findsWidgets);
    expect(find.text('KRW 2,500 / +3.10%'), findsOneWidget);
    expect(find.text('FILLED'), findsOneWidget);
    expect(find.text('OPEN'), findsOneWidget);
    expect(find.text('Mark Reviewed'), findsOneWidget);
    expect(find.text('Dismiss'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('queue card renders missing P/L percent as dash', (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(
      _FakeQueueApiClient(
        queue: KisShadowExitReviewQueue.fromJson(_queueJson(percent: null)),
      ),
    );

    await tester.pumpWidget(_wrap(controller));
    await tester.ensureVisible(find.text('Refresh Queue'));
    await tester.tap(find.text('Refresh Queue'));
    await tester.pumpAndSettle();

    expect(find.text('KRW 2,500 / --'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('queue item actions update local state without submit',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 3200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeQueueApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    await tester.ensureVisible(find.text('Refresh Queue'));
    await tester.tap(find.text('Refresh Queue'));
    await tester.pumpAndSettle();

    await tester.ensureVisible(find.text('Mark Reviewed'));
    await tester.tap(find.text('Mark Reviewed'));
    await tester.pumpAndSettle();

    expect(api.markReviewedCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);

    api.queue = KisShadowExitReviewQueue.fromJson(_queueJson(
      status: 'dismissed',
      reviewedCount: 0,
      dismissedCount: 1,
      openCount: 0,
    ));
    await tester.ensureVisible(find.text('Refresh Queue'));
    await tester.tap(find.text('Refresh Queue'));
    await tester.pumpAndSettle();

    expect(find.text('DISMISSED'), findsOneWidget);
    expect(find.text('Mark Reviewed'), findsNothing);
    expect(find.text('Dismiss'), findsNothing);

    controller.dispose();
  });
}

DashboardController _controller(_FakeQueueApiClient api) {
  return DashboardController(api, autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..krWatchlist = MarketWatchlist.empty('KR');
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => WatchlistSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeQueueApiClient extends ApiClient {
  _FakeQueueApiClient({KisShadowExitReviewQueue? queue})
      : queue = queue ?? KisShadowExitReviewQueue.fromJson(_queueJson());

  KisShadowExitReviewQueue queue;
  int fetchQueueCalls = 0;
  int markReviewedCalls = 0;
  int dismissCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisShadowExitReviewQueue> fetchKisShadowExitReviewQueue({
    int days = 30,
    int limit = 50,
  }) async {
    fetchQueueCalls += 1;
    return queue;
  }

  @override
  Future<KisShadowExitReviewQueueAction> markKisShadowExitQueueItemReviewed(
    String queueId, {
    String? note,
  }) async {
    markReviewedCalls += 1;
    queue = KisShadowExitReviewQueue.fromJson(_queueJson(
      status: 'reviewed',
      openCount: 0,
      reviewedCount: 1,
    ));
    return KisShadowExitReviewQueueAction.fromJson(_actionJson(
      status: 'reviewed',
    ));
  }

  @override
  Future<KisShadowExitReviewQueueAction> dismissKisShadowExitQueueItem(
    String queueId, {
    String? note,
  }) async {
    dismissCalls += 1;
    queue = KisShadowExitReviewQueue.fromJson(_queueJson(
      status: 'dismissed',
      openCount: 0,
      dismissedCount: 1,
    ));
    return KisShadowExitReviewQueueAction.fromJson(_actionJson(
      status: 'dismissed',
    ));
  }

  @override
  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    Map<String, dynamic>? sourceMetadata,
  }) async {
    validationCalls += 1;
    throw const ApiRequestException('validation should not run');
  }

  @override
  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    submitCalls += 1;
    throw const ApiRequestException('submit should not run');
  }
}

Map<String, dynamic> _queueJson({
  double? percent = 0.031,
  String status = 'open',
  int openCount = 2,
  int reviewedCount = 3,
  int dismissedCount = 1,
}) {
  return {
    'status': 'ok',
    'mode': 'shadow_exit_review_queue',
    'review_window_days': 30,
    'summary': {
      'open_count': openCount,
      'reviewed_count': reviewedCount,
      'dismissed_count': dismissedCount,
      'would_sell_open_count': openCount > 0 ? 1 : 0,
      'manual_review_open_count': openCount > 1 ? 1 : 0,
      'repeated_symbol_count': openCount > 0 ? 1 : 0,
      'latest_open_at': '2026-05-15T01:03:00+00:00',
    },
    'items': [
      {
        'queue_id': '005930:take_profit:cost_basis_pl_pct',
        'symbol': '005930',
        'decision': 'would_sell',
        'action': 'sell',
        'trigger': 'take_profit',
        'trigger_source': 'cost_basis_pl_pct',
        'severity': 'review',
        'occurrence_count': 3,
        'first_seen_at': '2026-05-15T01:00:00+00:00',
        'latest_seen_at': '2026-05-15T01:03:00+00:00',
        'latest_unrealized_pl': 2500,
        'latest_unrealized_pl_pct': percent,
        'latest_cost_basis': 70000,
        'latest_current_value': 72170,
        'latest_current_price': 72170,
        'suggested_quantity': 1,
        'reason':
            'Repeated shadow exit candidate. Manual operator review recommended.',
        'risk_flags': ['take_profit_triggered'],
        'gating_notes': ['shadow_exit_only', 'no_broker_submit'],
        'linked_manual_order_id': 44,
        'linked_manual_order_status': 'FILLED',
        'status': status,
        'operator_note': status == 'open' ? null : 'handled',
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
      }
    ],
    'safety': {
      'read_only': true,
      'operator_state_only': true,
      'creates_orders': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    },
  };
}

Map<String, dynamic> _actionJson({String status = 'reviewed'}) {
  return {
    'status': 'ok',
    'mode': 'shadow_exit_review_queue',
    'action': status == 'reviewed' ? 'mark-reviewed' : 'dismiss',
    'item': {
      'queue_id': '005930:take_profit:cost_basis_pl_pct',
      'symbol': '005930',
      'trigger': 'take_profit',
      'status': status,
      'operator_note': 'handled',
    },
    'safety': {
      'read_only': true,
      'operator_state_only': true,
      'creates_orders': false,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'auto_buy_enabled': false,
      'auto_sell_enabled': false,
      'scheduler_real_order_enabled': false,
    },
  };
}
