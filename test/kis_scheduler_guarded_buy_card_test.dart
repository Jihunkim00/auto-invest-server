import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_buy.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('scheduler guarded buy API calls buy-only endpoints', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_blockedJson()), 200);
      }),
    );

    final status = await client.fetchKisSchedulerGuardedBuyStatus();
    final result = await client.runKisSchedulerGuardedBuyOnce();

    expect(requests[0].method, 'GET');
    expect(requests[0].url.path, '/kis/scheduler/guarded-buy/status');
    expect(requests[1].method, 'POST');
    expect(requests[1].url.path, '/kis/scheduler/run-guarded-buy-once');
    expect(jsonDecode(requests[1].body), {
      'include_raw': false,
      'trigger_source': 'scheduler_manual_test',
    });
    expect(requests[1].url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(requests[1].url.path, isNot(contains('/kis/orders/validate')));
    expect(status.result, 'blocked');
    expect(result.mode, 'kis_scheduler_guarded_buy');
    expect(result.buyOnly, isTrue);
  });

  testWidgets('scheduler guarded buy card renders default off buy-only state',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeSchedulerGuardedBuyApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_buy_card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.text('KIS Scheduler Guarded Buy'),
      ),
      findsOneWidget,
    );
    for (final label in [
      'SCHEDULER GUARDED BUY',
      'BUY ONLY',
      'DEFAULT OFF',
      'SELL REVIEW FIRST',
      'SELL READY BLOCKS BUY',
      'REAL ORDERS REQUIRE EXPLICIT SETTINGS',
      'NO BROKER SUBMIT',
      'USES LIMITED AUTO BUY GATES',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }

    final runButton = find.descendant(
      of: card,
      matching: find.text('Run Scheduler Guarded Buy Once'),
    );
    await tester.ensureVisible(runButton);
    await tester.tap(runButton);
    await tester.pumpAndSettle();

    expect(api.runCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.descendant(of: card, matching: find.text('blocked')),
        findsWidgets);
    expect(
      find.descendant(
        of: card,
        matching: find.text('scheduler_real_orders_disabled'),
      ),
      findsWidgets,
    );
    expect(find.descendant(of: card, matching: find.text('Broker submit: No')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Manual submit: No')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.text('Real order submitted: No'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('scheduler guarded buy card renders sell-ready skip result',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerGuardedBuyApi())
      ..latestKisSchedulerGuardedBuyResult =
          KisSchedulerGuardedBuyResult.fromJson(_sellSkippedJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_buy_card'));
    expect(
        find.descendant(
            of: card,
            matching: find.text('SKIPPED: sell_review_required_before_buy')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.text('sell_review_required_before_buy'),
      ),
      findsWidgets,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('sell review: preview_only'),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('buy_result: skipped'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('scheduler guarded buy card renders submitted payload',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerGuardedBuyApi())
      ..latestKisSchedulerGuardedBuyResult =
          KisSchedulerGuardedBuyResult.fromJson(_submittedJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_buy_card'));
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('SUBMITTED BUY'),
      ),
      findsOneWidget,
    );
    expect(find.descendant(of: card, matching: find.text('buy')), findsWidgets);
    expect(
        find.descendant(of: card, matching: find.text('005930')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('321')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('KIS-ODNO-321')),
        findsWidgets);
    expect(find.descendant(of: card, matching: find.text('Broker submit: Yes')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('Manual submit: Yes')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.text('Real order submitted: Yes'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('scheduler guarded buy raw payload is collapsed by default',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerGuardedBuyApi())
      ..latestKisSchedulerGuardedBuyResult =
          KisSchedulerGuardedBuyResult.fromJson(_blockedJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_buy_card'));
    expect(
      find.descendant(of: card, matching: find.text('Developer Raw Payload')),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('"provider": "kis"'),
      ),
      findsNothing,
    );

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 9200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(_FakeSchedulerGuardedBuyApi api) {
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
          builder: (context, _) => TestLabSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeSchedulerGuardedBuyApi extends ApiClient {
  _FakeSchedulerGuardedBuyApi({KisSchedulerGuardedBuyResult? result})
      : result =
            result ?? KisSchedulerGuardedBuyResult.fromJson(_blockedJson());

  KisSchedulerGuardedBuyResult result;
  int statusCalls = 0;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerGuardedBuyResult>
      fetchKisSchedulerGuardedBuyStatus() async {
    statusCalls += 1;
    return result;
  }

  @override
  Future<KisSchedulerGuardedBuyResult> runKisSchedulerGuardedBuyOnce({
    String? slotLabel,
    bool includeRaw = false,
    String triggerSource = 'scheduler_manual_test',
  }) async {
    runCalls += 1;
    return result;
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

  @override
  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async =>
      KisSchedulerSimulationStatus.safeDefault();

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

Map<String, dynamic> _blockedJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'kis_scheduler_guarded_buy',
    'source': 'kis_scheduler_guarded_buy',
    'source_type': 'scheduler_guarded_buy_execution',
    'trigger_source': 'scheduler_guarded_buy',
    'requested_trigger_source': 'scheduler_manual_test',
    'slot_label': 'manual_guarded_buy',
    'buy_only': true,
    'scheduler_buy_only': true,
    'sell_priority_required': true,
    'sell_priority_checked': true,
    'sell_ready_blocks_buy': true,
    'sell_review_required_before_buy': true,
    'scheduler_buy_enabled': false,
    'scheduler_real_orders_enabled': false,
    'real_order_submit_allowed': false,
    'buy_execution_allowed': false,
    'result': 'blocked',
    'action': 'hold',
    'reason': 'scheduler_real_orders_disabled',
    'primary_block_reason': 'scheduler_real_orders_disabled',
    'summary': {
      'result': 'blocked',
      'action': 'hold',
      'primary_block_reason': 'scheduler_real_orders_disabled',
      'buy_only': true,
      'sell_priority_checked': true,
      'sell_ready_blocks_buy': true,
      'scheduler_real_orders_enabled': false,
      'scheduler_buy_enabled': false,
      'daily_limit_remaining': 1,
    },
    'sell_review_result': {
      'result': 'blocked',
      'action': 'hold',
      'reason': 'no_held_position',
    },
    'buy_result': {
      'result': 'skipped',
      'action': 'hold',
      'reason': 'scheduler_buy_gates_blocked',
      'primary_block_reason': 'scheduler_real_orders_disabled',
      'buy_execution_skipped': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
    },
    'block_reasons': [
      'scheduler_real_orders_disabled',
      'scheduler_buy_disabled',
    ],
    'checks': {
      'kis_scheduler_allow_real_orders': false,
      'configured_kis_scheduler_allow_real_orders': false,
      'kis_scheduler_buy_enabled': false,
      'dry_run': true,
      'kill_switch': false,
      'kis_real_order_enabled': false,
      'kis_live_auto_buy_enabled': false,
      'kis_limited_auto_buy_enabled': false,
      'entry_allowed_now': false,
    },
    'safety': {
      'scheduler_buy_only': true,
      'buy_only': true,
      'sell_priority_required': true,
      'sell_review_completed': true,
      'sell_ready_blocks_buy': true,
      'no_direct_broker_submit_from_scheduler': true,
      'no_direct_manual_submit_from_scheduler': true,
      'existing_limited_auto_buy_path_reused': true,
      'scheduler_real_orders_enabled': false,
      'dry_run': true,
      'kill_switch': false,
      'kis_real_order_enabled': false,
      'kis_live_auto_buy_enabled': false,
      'kis_limited_auto_buy_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'kis_scheduler_buy_enabled': false,
      'daily_limit_remaining': 1,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
    },
    'daily_limit': {
      'max_orders_per_day': 1,
      'submitted_count_today': 0,
      'daily_limit_remaining': 1,
      'daily_limit_reached': false,
    },
    'duplicate_order_check': {
      'checked': false,
      'duplicate_open_buy_order': false,
    },
    'market_session_check': {
      'checked': false,
      'entry_allowed_now': false,
      'no_new_entry_after': '14:50',
    },
    'diagnostics': {'limited_auto_buy_result_available': false},
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  };
}

Map<String, dynamic> _sellSkippedJson() {
  return {
    ..._blockedJson(),
    'scheduler_buy_enabled': true,
    'scheduler_real_orders_enabled': true,
    'result': 'skipped',
    'reason': 'sell_review_required_before_buy',
    'primary_block_reason': 'sell_review_required_before_buy',
    'block_reasons': ['sell_review_required_before_buy'],
    'summary': {
      'result': 'skipped',
      'action': 'hold',
      'primary_block_reason': 'sell_review_required_before_buy',
      'buy_only': true,
      'sell_priority_checked': true,
      'sell_ready_blocks_buy': true,
      'scheduler_real_orders_enabled': true,
      'scheduler_buy_enabled': true,
      'daily_limit_remaining': 1,
    },
    'sell_review_result': {
      'result': 'preview_only',
      'action': 'sell_ready',
      'reason': 'stop_loss_candidate_ready_read_only',
      'symbol': '005930',
      'final_candidate': {'status': 'SELL_READY'},
    },
    'buy_result': {
      'result': 'skipped',
      'action': 'hold',
      'reason': 'sell_review_required_before_buy',
      'primary_block_reason': 'sell_review_required_before_buy',
      'buy_execution_skipped': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
    },
    'checks': {
      'kis_scheduler_allow_real_orders': true,
      'configured_kis_scheduler_allow_real_orders': true,
      'kis_scheduler_buy_enabled': true,
      'dry_run': false,
      'kill_switch': false,
      'kis_real_order_enabled': true,
      'kis_live_auto_buy_enabled': true,
      'kis_limited_auto_buy_enabled': true,
      'entry_allowed_now': true,
    },
    'safety': {
      ...Map<String, dynamic>.from(_blockedJson()['safety'] as Map),
      'scheduler_real_orders_enabled': true,
      'dry_run': false,
      'kis_real_order_enabled': true,
      'kis_live_auto_buy_enabled': true,
      'kis_limited_auto_buy_enabled': true,
      'kis_scheduler_allow_real_orders': true,
      'kis_scheduler_buy_enabled': true,
    },
  };
}

Map<String, dynamic> _submittedJson() {
  return {
    ..._sellSkippedJson(),
    'real_order_submit_allowed': true,
    'buy_execution_allowed': true,
    'result': 'submitted',
    'action': 'buy',
    'reason': 'scheduler_guarded_buy_submitted',
    'primary_block_reason': null,
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'quantity': 4,
    'estimated_notional': 288000,
    'order_id': 321,
    'broker_order_id': 'BRK-321',
    'kis_odno': 'KIS-ODNO-321',
    'real_order_submitted': true,
    'broker_submit_called': true,
    'manual_submit_called': true,
    'block_reasons': [],
    'summary': {
      'result': 'submitted',
      'action': 'buy',
      'buy_only': true,
      'sell_priority_checked': true,
      'sell_ready_blocks_buy': true,
      'scheduler_real_orders_enabled': true,
      'scheduler_buy_enabled': true,
      'daily_limit_remaining': 0,
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'quantity': 4,
      'estimated_notional': 288000,
      'order_id': 321,
      'broker_order_id': 'BRK-321',
      'kis_odno': 'KIS-ODNO-321',
    },
    'sell_review_result': {
      'result': 'blocked',
      'action': 'hold',
      'reason': 'no_held_position',
    },
    'buy_result': {
      'result': 'submitted',
      'action': 'buy',
      'reason': 'guarded_limited_auto_buy_submitted',
      'source': 'kis_limited_auto_buy',
      'source_type': 'guarded_limited_auto_buy',
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'quantity': 4,
      'estimated_notional': 288000,
      'order_id': 321,
      'broker_order_id': 'BRK-321',
      'kis_odno': 'KIS-ODNO-321',
      'real_order_submit_allowed': true,
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
    },
    'safety': {
      ...Map<String, dynamic>.from(_sellSkippedJson()['safety'] as Map),
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
      'daily_limit_remaining': 0,
    },
    'daily_limit': {
      'max_orders_per_day': 1,
      'submitted_count_today': 1,
      'daily_limit_remaining': 0,
      'daily_limit_reached': true,
    },
    'duplicate_order_check': {
      'checked': true,
      'duplicate_open_buy_order': false,
    },
    'market_session_check': {
      'checked': true,
      'entry_allowed_now': true,
      'no_new_entry_after': '14:50',
    },
  };
}
