import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/order_ticket_section.dart';
import 'package:auto_invest_dashboard/models/kis_live_exit_preflight.dart';

void main() {
  test('manual validation request includes safe exit preflight metadata',
      () async {
    late Map<String, dynamic> captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode(_validationResponse()), 200);
      }),
    );

    await client.validateKisOrder(
      symbol: '005930',
      side: 'sell',
      qty: 2,
      sourceMetadata: _sourceMetadata(),
    );

    expect(captured['symbol'], '005930');
    expect(captured['side'], 'sell');
    expect(captured['qty'], 2);
    expect(captured['source_metadata']['source'], 'kis_live_exit_preflight');
    expect(captured['source_metadata']['source_type'], 'manual_confirm_exit');
    expect(captured['source_metadata']['exit_trigger'], 'stop_loss');
    expect(captured['source_metadata']['auto_sell_enabled'], isFalse);
    expect(captured.toString(), isNot(contains('appsecret')));
    expect(captured.toString(), isNot(contains('access_token')));
  });

  test('manual submit request includes source metadata only on manual path',
      () async {
    late http.Request captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = request;
        return http.Response(jsonEncode(_submitResponse()), 200);
      }),
    );

    await client.submitKisManualOrder(
      symbol: '005930',
      side: 'sell',
      qty: 2,
      confirmLive: true,
      sourceMetadata: _sourceMetadata(),
    );

    final body = jsonDecode(captured.body) as Map<String, dynamic>;
    expect(captured.url.path, '/kis/orders/manual-submit');
    expect(body['confirm_live'], isTrue);
    expect(body['source_metadata']['source'], 'kis_live_exit_preflight');
    expect(body['source_metadata']['trigger_source'], 'cost_basis_pl_pct');
    expect(body.toString(), isNot(contains('appsecret')));
    expect(body.toString(), isNot(contains('access_token')));
  });

  test('manual validation request includes safe shadow exit metadata',
      () async {
    late Map<String, dynamic> captured;
    final client = ApiClient(
      client: MockClient((request) async {
        captured = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response(jsonEncode(_validationResponse()), 200);
      }),
    );

    await client.validateKisOrder(
      symbol: '005930',
      side: 'sell',
      qty: 2,
      sourceMetadata: _shadowSourceMetadata(),
    );

    expect(captured['source_metadata']['source'], 'kis_exit_shadow_decision');
    expect(
        captured['source_metadata']['source_type'], 'dry_run_sell_simulation');
    expect(captured['source_metadata']['exit_trigger'], 'stop_loss');
    expect(captured['source_metadata']['shadow_real_order_submitted'], isFalse);
    expect(captured['source_metadata']['shadow_broker_submit_called'], isFalse);
    expect(captured['source_metadata']['shadow_manual_submit_called'], isFalse);
    expect(captured['source_metadata']['auto_sell_enabled'], isFalse);
    expect(captured.toString(), isNot(contains('appsecret')));
    expect(captured.toString(), isNot(contains('access_token')));
  });

  testWidgets('prepared manual sell ticket shows audit guardrails',
      (tester) async {
    tester.view.physicalSize = const Size(1200, 2200);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final controller = DashboardController(_NoopApiClient(), autoload: false);
    controller.prepareKisManualSellFromExitCandidate(
      const KisLiveExitCandidate(
        symbol: '005930',
        side: 'sell',
        suggestedQuantity: 2,
        trigger: 'stop_loss',
        triggerSource: 'cost_basis_pl_pct',
        severity: 'review',
        actionHint: 'manual_confirm_sell',
        reason: 'Manual confirmation is required.',
        submitReady: false,
        manualConfirmRequired: true,
        realOrderSubmitAllowed: false,
        realOrderSubmitted: false,
        brokerSubmitCalled: false,
        manualSubmitCalled: false,
      ),
    );

    await tester.pumpWidget(MaterialApp(
      theme: ThemeData.dark(),
      home: Scaffold(body: OrderTicketSection(controller: controller)),
    ));

    expect(find.text('Prepared from exit preflight'), findsOneWidget);
    expect(find.text('MANUAL CONFIRMATION REQUIRED'), findsOneWidget);
    expect(find.text('NO AUTO SELL'), findsOneWidget);
    expect(find.text('VALIDATE BEFORE SUBMIT'), findsOneWidget);
    expect(find.text('confirm_live required'), findsOneWidget);
    expect(controller.kisLiveConfirmation, isFalse);

    controller.dispose();
  });
}

Map<String, dynamic> _sourceMetadata() {
  return {
    'source': 'kis_live_exit_preflight',
    'source_type': 'manual_confirm_exit',
    'exit_trigger': 'stop_loss',
    'trigger_source': 'cost_basis_pl_pct',
    'suggested_quantity': 2,
    'risk_flags': ['stop_loss_triggered'],
    'gating_notes': ['manual_confirm_required', 'no_auto_submit'],
    'manual_confirm_required': true,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'real_order_submit_allowed': false,
    'appsecret': 'must-not-send',
    'access_token': 'must-not-send',
  };
}

Map<String, dynamic> _shadowSourceMetadata() {
  return {
    'source': 'kis_exit_shadow_decision',
    'source_type': 'dry_run_sell_simulation',
    'exit_trigger': 'stop_loss',
    'trigger_source': 'cost_basis_pl_pct',
    'suggested_quantity': 2,
    'risk_flags': ['stop_loss_triggered'],
    'gating_notes': ['shadow_exit_only', 'no_broker_submit'],
    'manual_confirm_required': true,
    'auto_sell_enabled': false,
    'scheduler_real_order_enabled': false,
    'real_order_submit_allowed': false,
    'shadow_real_order_submitted': false,
    'shadow_broker_submit_called': false,
    'shadow_manual_submit_called': false,
    'appsecret': 'must-not-send',
    'access_token': 'must-not-send',
  };
}

Map<String, dynamic> _validationResponse() {
  return {
    'provider': 'kis',
    'market': 'KR',
    'environment': 'prod',
    'dry_run': true,
    'validated_for_submission': true,
    'can_submit_later': true,
    'symbol': '005930',
    'side': 'sell',
    'qty': 2,
    'order_type': 'market',
    'current_price': 72000,
    'estimated_amount': 144000,
    'available_cash': null,
    'held_qty': 3,
    'warnings': [],
    'block_reasons': [],
    'market_session': {
      'market': 'KR',
      'timezone': 'Asia/Seoul',
      'is_market_open': true,
      'is_entry_allowed_now': true,
      'is_near_close': false,
    },
    'order_preview': {
      'account_no_masked': '12****78',
      'product_code': '01',
      'symbol': '005930',
      'side': 'sell',
      'qty': 2,
      'order_type': 'market',
      'kis_tr_id_preview': 'TTTC0801U',
      'payload_preview': {'PDNO': '005930'},
    },
    'source_metadata': _sourceMetadata(),
  };
}

Map<String, dynamic> _submitResponse() {
  return {
    'order_id': 1,
    'broker': 'kis',
    'market': 'KR',
    'symbol': '005930',
    'side': 'sell',
    'order_type': 'market',
    'requested_qty': 2,
    'filled_qty': 0,
    'remaining_qty': 2,
    'avg_fill_price': null,
    'kis_odno': '0001234567',
    'internal_status': 'SUBMITTED',
    'broker_order_status': 'submitted',
    'created_at': '2026-05-14T01:00:00',
    'submitted_at': '2026-05-14T01:00:01',
    'filled_at': null,
    'canceled_at': null,
    'last_synced_at': null,
    'sync_error': null,
    'display_status': 'Submitted',
    'clear_status': 'SUBMITTED',
    'is_syncable': true,
    'is_terminal': false,
    'source': 'kis_live_exit_preflight',
    'source_metadata': _sourceMetadata(),
  };
}

class _NoopApiClient extends ApiClient {}
