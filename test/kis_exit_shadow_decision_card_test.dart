import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_exit_shadow_decision.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_result.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/order_validation_result.dart';
import 'package:auto_invest_dashboard/models/trading_run.dart';

void main() {
  test('runKisExitShadowOnce posts shadow endpoint only', () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_shadowJson()), 200);
      }),
    );

    final result = await client.runKisExitShadowOnce();

    expect(captured.method, 'POST');
    expect(captured.url.path, '/kis/exit-shadow/run-once');
    expect(captured.url.path, isNot(contains('/kis/orders/manual-submit')));
    expect(captured.url.path, isNot(contains('/kis/orders/submit-manual')));
    expect(captured.url.path, isNot(contains('/kis/orders/validate')));
    expect(captured.body, '{}');
    expect(captured.body, isNot(contains('symbol')));
    expect(captured.body, isNot(contains('qty')));
    expect(captured.body, isNot(contains('side')));
    expect(result.mode, 'shadow_exit_dry_run');
    expect(result.realOrderSubmitted, isFalse);
  });

  testWidgets('shadow card shows required dry-run labels', (tester) async {
    final controller = _controller(_FakeShadowApiClient());

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('KIS Exit Shadow Decision'), findsOneWidget);
    expect(find.text('SHADOW EXIT ONLY'), findsOneWidget);
    expect(find.text('DRY-RUN SELL SIMULATION'), findsOneWidget);
    expect(find.text('NO BROKER SUBMIT'), findsWidgets);
    expect(find.text('NO MANUAL SUBMIT'), findsOneWidget);
    expect(find.text('LIVE AUTO SELL DISABLED'), findsOneWidget);
    expect(find.text('SCHEDULER REAL ORDERS DISABLED'), findsWidgets);
    expect(find.text('Run Shadow Exit Once'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    controller.dispose();
  });

  testWidgets(
      'run shadow exit displays would-sell candidate without validation',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final api = _FakeShadowApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Shadow Exit Once'));
    await tester.tap(find.text('Run Shadow Exit Once'));
    await tester.pumpAndSettle();

    expect(api.shadowCalls, 1);
    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(find.textContaining('WOULD SELL'), findsWidgets);
    expect(find.text('005930'), findsWidgets);
    expect(find.text('stop_loss'), findsWidgets);
    expect(find.text('-2.00%'), findsWidgets);
    expect(find.text('real_order_submitted=false'), findsWidgets);
    expect(find.text('broker_submit_called=false'), findsWidgets);
    expect(find.text('manual_submit_called=false'), findsWidgets);
    expect(find.text('real_order_submit_allowed=false'), findsWidgets);
    expect(find.text('Prepare Manual Sell Ticket'), findsOneWidget);
    expect(find.text('Submit Live KIS Order'), findsNothing);

    await tester.ensureVisible(find.text('Prepare Manual Sell Ticket'));
    await tester.tap(find.text('Prepare Manual Sell Ticket'));
    await tester.pumpAndSettle();

    expect(api.validationCalls, 0);
    expect(api.submitCalls, 0);
    expect(controller.orderTicketSymbol, '005930');
    expect(controller.orderTicketSide, 'sell');
    expect(controller.orderTicketQty, 2);
    expect(controller.kisLiveConfirmation, isFalse);
    expect(controller.orderTicketSourceMetadata?['source'],
        'kis_exit_shadow_decision');
    expect(controller.orderTicketSourceMetadata?['source_type'],
        'dry_run_sell_simulation');
    expect(controller.orderTicketSourceMetadata?['shadow_real_order_submitted'],
        isFalse);

    controller.dispose();
  });

  testWidgets('hold shadow decision displays safely without candidate',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = _controller(_FakeShadowApiClient(
      result: KisExitShadowDecision.fromJson(_shadowHoldJson()),
    ));

    await tester.pumpWidget(_wrap(controller));

    await tester.ensureVisible(find.text('Run Shadow Exit Once'));
    await tester.tap(find.text('Run Shadow Exit Once'));
    await tester.pumpAndSettle();

    expect(find.text('HOLD. No shadow sell candidate was selected.'),
        findsOneWidget);
    expect(find.text('Prepare Manual Sell Ticket'), findsNothing);

    controller.dispose();
  });
}

DashboardController _controller(_FakeShadowApiClient api) {
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

class _FakeShadowApiClient extends ApiClient {
  _FakeShadowApiClient({KisExitShadowDecision? result})
      : result = result ?? KisExitShadowDecision.fromJson(_shadowJson());

  final KisExitShadowDecision result;
  int shadowCalls = 0;
  int validationCalls = 0;
  int submitCalls = 0;

  @override
  Future<KisExitShadowDecision> runKisExitShadowOnce() async {
    shadowCalls += 1;
    return result;
  }

  @override
  Future<List<TradingRun>> getRecentTradingRuns() async => const [];

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

Map<String, dynamic> _shadowJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'shadow_exit_dry_run',
    'source': 'kis_exit_shadow_decision',
    'source_type': 'dry_run_sell_simulation',
    'decision': 'would_sell',
    'action': 'sell',
    'reason': 'would_sell_stop_loss',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'real_order_submit_allowed': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'manual_confirm_required': true,
    'created_at': '2026-05-15T01:00:00+00:00',
    'candidate': {
      'symbol': '005930',
      'side': 'sell',
      'quantity_available': 2,
      'suggested_quantity': 2,
      'trigger': 'stop_loss',
      'trigger_source': 'cost_basis_pl_pct',
      'current_price': 70560,
      'cost_basis': 144000,
      'current_value': 141120,
      'unrealized_pl': -2880,
      'unrealized_pl_pct': -0.02,
      'reason': 'Shadow decision only.',
      'risk_flags': ['stop_loss_triggered'],
      'gating_notes': ['shadow_exit_only', 'no_broker_submit'],
      'real_order_submitted': false,
      'broker_submit_called': false,
      'manual_submit_called': false,
      'real_order_submit_allowed': false,
      'manual_confirm_required': true,
      'audit_metadata': {
        'source': 'kis_exit_shadow_decision',
        'source_type': 'dry_run_sell_simulation',
        'exit_trigger': 'stop_loss',
        'trigger_source': 'cost_basis_pl_pct',
        'shadow_real_order_submitted': false,
      },
    },
    'risk_flags': ['shadow_exit_only', 'stop_loss_triggered'],
    'gating_notes': ['shadow_exit_only', 'no_broker_submit'],
  };
}

Map<String, dynamic> _shadowHoldJson() {
  return {
    'status': 'ok',
    'provider': 'kis',
    'market': 'KR',
    'mode': 'shadow_exit_dry_run',
    'source': 'kis_exit_shadow_decision',
    'source_type': 'dry_run_sell_simulation',
    'decision': 'hold',
    'action': 'hold',
    'reason': 'no_exit_condition',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'real_order_submit_allowed': false,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'manual_confirm_required': true,
    'candidate': null,
    'candidates_evaluated': [
      {
        'symbol': '005930',
        'side': 'sell',
        'trigger': 'none',
        'trigger_source': 'cost_basis_pl_pct',
        'cost_basis': null,
        'unrealized_pl_pct': null,
      }
    ],
  };
}
