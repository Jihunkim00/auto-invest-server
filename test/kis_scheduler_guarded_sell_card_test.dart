import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_simulation.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('scheduler guarded sell API calls sell-only endpoints', () async {
    final requests = <http.Request>[];
    final client = ApiClient(
      client: MockClient((request) async {
        requests.add(request);
        return http.Response(jsonEncode(_blockedJson()), 200);
      }),
    );

    final status = await client.fetchKisSchedulerGuardedSellStatus();
    final result = await client.runKisSchedulerGuardedSellOnce();

    expect(requests[0].method, 'GET');
    expect(requests[0].url.path, '/kis/scheduler/guarded-sell/status');
    expect(requests[1].method, 'POST');
    expect(requests[1].url.path, '/kis/scheduler/run-guarded-sell-once');
    expect(jsonDecode(requests[1].body), {
      'include_raw': false,
      'trigger_source': 'scheduler_manual_test',
    });
    expect(requests[1].url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(requests[1].url.path, isNot(contains('/kis/orders/validate')));
    expect(requests[1].url.path, isNot(contains('limited-auto-buy')));
    expect(status.result, 'blocked');
    expect(result.mode, 'kis_scheduler_guarded_sell');
    expect(result.buyExecutionAllowed, isFalse);
  });

  testWidgets('scheduler guarded sell card renders default off sell-only state',
      (tester) async {
    await _setLargeView(tester);
    final api = _FakeSchedulerGuardedSellApi();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_sell_card'));
    expect(card, findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.text('KIS Scheduler Guarded Sell'),
      ),
      findsOneWidget,
    );
    for (final label in [
      'SCHEDULER GUARDED SELL',
      'SELL ONLY',
      'DEFAULT OFF',
      'BUY DISABLED',
      'REAL ORDERS REQUIRE EXPLICIT SETTINGS',
      'NO BROKER SUBMIT',
      'USES LIMITED AUTO SELL GATES',
    ]) {
      expect(
          find.descendant(of: card, matching: find.text(label)), findsWidgets);
    }
    expect(
      find.descendant(
        of: card,
        matching: find.text('BUY DISABLED FOR SCHEDULER SELL-ONLY'),
      ),
      findsOneWidget,
    );

    final runButton = find.descendant(
      of: card,
      matching: find.text('Run Scheduler Guarded Sell Once'),
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

  testWidgets('scheduler guarded sell card renders submitted payload',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerGuardedSellApi())
      ..latestKisSchedulerGuardedSellResult =
          KisSchedulerGuardedSellResult.fromJson(_submittedJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_sell_card'));
    expect(find.descendant(of: card, matching: find.text('SUBMITTED')),
        findsNothing);
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining('SUBMITTED SELL'),
      ),
      findsOneWidget,
    );
    expect(
        find.descendant(of: card, matching: find.text('sell')), findsWidgets);
    expect(
        find.descendant(of: card, matching: find.text('005930')), findsWidgets);
    expect(find.descendant(of: card, matching: find.text('stop_loss')),
        findsWidgets);
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

  testWidgets('scheduler guarded sell raw payload is collapsed by default',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller(_FakeSchedulerGuardedSellApi())
      ..latestKisSchedulerGuardedSellResult =
          KisSchedulerGuardedSellResult.fromJson(_blockedJson());

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_scheduler_guarded_sell_card'));
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
  tester.view.physicalSize = const Size(1200, 8200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller(_FakeSchedulerGuardedSellApi api) {
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
          builder: (context, _) => TestLabSection(
              controller: controller, advancedInitiallyExpanded: true),
        ),
      ),
    ),
  );
}

class _FakeSchedulerGuardedSellApi extends ApiClient {
  _FakeSchedulerGuardedSellApi({KisSchedulerGuardedSellResult? result})
      : result =
            result ?? KisSchedulerGuardedSellResult.fromJson(_blockedJson());

  KisSchedulerGuardedSellResult result;
  int statusCalls = 0;
  int runCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisSchedulerGuardedSellResult>
      fetchKisSchedulerGuardedSellStatus() async {
    statusCalls += 1;
    return result;
  }

  @override
  Future<KisSchedulerGuardedSellResult> runKisSchedulerGuardedSellOnce({
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
    'mode': 'kis_scheduler_guarded_sell',
    'trigger_source': 'scheduler_guarded_sell',
    'requested_trigger_source': 'scheduler_manual_test',
    'slot_label': 'manual_guarded_sell',
    'sell_only': true,
    'scheduler_sell_only': true,
    'buy_execution_allowed': false,
    'scheduler_buy_execution_blocked': true,
    'scheduler_real_orders_enabled': false,
    'real_order_submit_allowed': false,
    'result': 'blocked',
    'action': 'hold',
    'reason': 'scheduler_real_orders_disabled',
    'primary_block_reason': 'scheduler_real_orders_disabled',
    'summary': {
      'result': 'blocked',
      'action': 'hold',
      'primary_block_reason': 'scheduler_real_orders_disabled',
      'sell_only': true,
      'buy_execution_allowed': false,
      'scheduler_real_orders_enabled': false,
      'scheduler_sell_enabled': false,
      'daily_limit_remaining': 1,
    },
    'sell_result': null,
    'buy_result': {
      'result': 'skipped',
      'action': 'hold',
      'reason': 'buy_scheduler_execution_disabled',
      'skipped_for_sell_only_scheduler': true,
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'validation_called': false,
    },
    'block_reasons': [
      'scheduler_real_orders_disabled',
      'scheduler_sell_disabled',
    ],
    'checks': {
      'kis_scheduler_allow_real_orders': false,
      'configured_kis_scheduler_allow_real_orders': false,
      'kis_scheduler_sell_enabled': false,
      'dry_run': true,
      'kill_switch': false,
      'kis_real_order_enabled': false,
      'kis_live_auto_sell_enabled': false,
      'kis_limited_auto_stop_loss_enabled': false,
      'kis_limited_auto_take_profit_enabled': false,
      'sell_session_allowed': false,
    },
    'safety': {
      'scheduler_sell_only': true,
      'buy_execution_allowed': false,
      'scheduler_buy_execution_blocked': true,
      'no_direct_broker_submit_from_scheduler': true,
      'no_direct_manual_submit_from_scheduler': true,
      'existing_limited_auto_sell_path_reused': true,
      'limited_auto_buy_not_called_in_submit_mode': true,
      'scheduler_real_orders_enabled': false,
      'dry_run': true,
      'kill_switch': false,
      'kis_real_order_enabled': false,
      'kis_live_auto_sell_enabled': false,
      'kis_scheduler_allow_real_orders': false,
      'kis_scheduler_sell_enabled': false,
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
      'duplicate_open_sell_order': false,
    },
    'market_session_check': {
      'checked': false,
      'sell_session_allowed': false,
    },
    'diagnostics': {'buy_module': 'skipped_for_sell_only_scheduler'},
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
  };
}

Map<String, dynamic> _submittedJson() {
  return {
    ..._blockedJson(),
    'scheduler_real_orders_enabled': true,
    'real_order_submit_allowed': true,
    'result': 'submitted',
    'action': 'sell',
    'reason': 'scheduler_guarded_sell_submitted',
    'primary_block_reason': null,
    'symbol': '005930',
    'company_name': 'Samsung Electronics',
    'quantity': 3,
    'trigger': 'stop_loss',
    'order_id': 321,
    'broker_order_id': 'BRK-321',
    'kis_odno': 'KIS-ODNO-321',
    'real_order_submitted': true,
    'broker_submit_called': true,
    'manual_submit_called': true,
    'block_reasons': [],
    'summary': {
      'result': 'submitted',
      'action': 'sell',
      'sell_only': true,
      'buy_execution_allowed': false,
      'scheduler_real_orders_enabled': true,
      'scheduler_sell_enabled': true,
      'daily_limit_remaining': 0,
      'symbol': '005930',
      'quantity': 3,
      'trigger': 'stop_loss',
      'order_id': 321,
      'broker_order_id': 'BRK-321',
      'kis_odno': 'KIS-ODNO-321',
    },
    'sell_result': {
      'result': 'submitted',
      'action': 'sell',
      'reason': 'submitted',
      'source': 'kis_limited_auto_stop_loss',
      'source_type': 'guarded_stop_loss_auto_sell',
      'symbol': '005930',
      'quantity': 3,
      'trigger': 'stop_loss',
      'order_id': 321,
      'broker_order_id': 'BRK-321',
      'kis_odno': 'KIS-ODNO-321',
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
    },
    'checks': {
      'kis_scheduler_allow_real_orders': true,
      'configured_kis_scheduler_allow_real_orders': true,
      'kis_scheduler_sell_enabled': true,
      'dry_run': false,
      'kill_switch': false,
      'kis_real_order_enabled': true,
      'kis_live_auto_sell_enabled': true,
      'kis_limited_auto_stop_loss_enabled': true,
      'kis_limited_auto_take_profit_enabled': false,
      'sell_session_allowed': true,
    },
    'safety': {
      'scheduler_sell_only': true,
      'buy_execution_allowed': false,
      'scheduler_buy_execution_blocked': true,
      'no_direct_broker_submit_from_scheduler': true,
      'no_direct_manual_submit_from_scheduler': true,
      'existing_limited_auto_sell_path_reused': true,
      'limited_auto_buy_not_called_in_submit_mode': true,
      'scheduler_real_orders_enabled': true,
      'dry_run': false,
      'kill_switch': false,
      'kis_real_order_enabled': true,
      'kis_live_auto_sell_enabled': true,
      'kis_scheduler_allow_real_orders': true,
      'kis_scheduler_sell_enabled': true,
      'daily_limit_remaining': 0,
      'real_order_submitted': true,
      'broker_submit_called': true,
      'manual_submit_called': true,
    },
    'daily_limit': {
      'max_orders_per_day': 1,
      'submitted_count_today': 1,
      'daily_limit_remaining': 0,
      'daily_limit_reached': true,
    },
    'duplicate_order_check': {
      'checked': true,
      'duplicate_open_sell_order': false,
    },
    'market_session_check': {
      'checked': true,
      'sell_session_allowed': true,
    },
  };
}
