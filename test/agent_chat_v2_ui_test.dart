import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/ai/ai_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_v2_response.dart';

void main() {
  testWidgets('AI quick action renders analysis card from V2 response',
      (tester) async {
    final api = _FakeV2Api();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      MaterialApp(home: AiScreen(controller: controller)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('ai-quick-종목 분석')));
    await tester.pumpAndSettle();

    expect(api.messages, ['삼성전자 분석해줘']);
    expect(
        find.byKey(const ValueKey('ai-v2-assistant-message')), findsOneWidget);
    expect(find.byKey(const ValueKey('ai-v2-analysis-card')), findsOneWidget);
    expect(find.text('관망'), findsWidgets);
  });

  testWidgets('AI trade prepare renders preview confirmation card',
      (tester) async {
    final api = _FakeV2Api(tradePrepare: true);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      MaterialApp(home: AiScreen(controller: controller)),
    );
    await tester.pumpAndSettle();

    await tester.enterText(
      find.byKey(const ValueKey('ai-v2-input')),
      '삼성전자 3주 사고 싶어',
    );
    await tester.tap(find.byKey(const ValueKey('ai-v2-send')));
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('agent-chat-live-order-card')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('agent-chat-live-order-confirm')),
        findsOneWidget);
    expect(find.text('주문 준비가 완료되었습니다.'), findsOneWidget);
  });

  testWidgets('AI controls wrap at phone width with larger text',
      (tester) async {
    tester.view.physicalSize = const Size(430, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final controller = DashboardController(_FakeV2Api(), autoload: false);

    await tester.pumpWidget(
      MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(1.3)),
          child: child!,
        ),
        home: AiScreen(controller: controller),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(ActionChip), findsNWidgets(5));
    await tester.enterText(
      find.byKey(const ValueKey('ai-v2-input')),
      '삼성전자 최근 실적과 위험 요인을 자세히 설명해 주세요. '
      '긴 한국어 질문도 화면 밖으로 잘리지 않아야 합니다.',
    );
    await tester.tap(find.byKey(const ValueKey('ai-v2-send')));
    await tester.pumpAndSettle();

    final userMessage = find.byKey(const ValueKey('ai-v2-user-message'));
    expect(userMessage, findsOneWidget);
    expect(tester.getSize(userMessage).width, lessThanOrEqualTo(398));
    expect(find.byKey(const ValueKey('ai-v2-analysis-card')), findsOneWidget);
    expect(tester.takeException(), isNull);
    controller.dispose();
  });
}

class _FakeV2Api extends ApiClient {
  _FakeV2Api({this.tradePrepare = false});

  final bool tradePrepare;
  final List<String> messages = [];

  @override
  Future<AgentChatV2Response> sendAgentChatV2Message({
    required String message,
    String? conversationKey,
    Map<String, dynamic>? context,
    bool autoCreateConversation = true,
    String language = 'ko',
    String locale = 'ko-KR',
  }) async {
    messages.add(message);
    return AgentChatV2Response.fromJson(
      tradePrepare
          ? {
              'intent': 'trade_prepare',
              'status': 'confirmation_required',
              'message': '주문 준비가 완료되었습니다.',
              'conversation_key': 'conv_v2_flutter',
              'symbol': '005930',
              'symbol_name': '삼성전자',
              'market': 'KR',
              'requires_confirmation': true,
              'order_preview': {
                'action_id': 7,
                'status': 'pending_confirmation',
                'action_type': 'chat_confirmed_live_order',
                'conversation_key': 'conv_v2_flutter',
                'provider': 'kis',
                'market': 'KR',
                'symbol': '005930',
                'symbol_name': '삼성전자',
                'side': 'buy',
                'order_type': 'market',
                'quantity': 3,
                'estimated_price': 60000,
                'estimated_notional': 180000,
                'currency': 'KRW',
                'confirmation_phrase': '005930 buy 3 confirm',
                'safety_controls': {'dry_run': true, 'kill_switch': true},
              },
              'available_actions': [
                'confirm_live_order',
                'cancel_live_order',
              ],
              'safety': {
                'real_order_submitted': false,
                'broker_submit_called': false,
                'setting_changed': false,
              },
            }
          : {
              'intent': 'analyze',
              'status': 'completed',
              'message': '삼성전자 현재 판단은 HOLD입니다.',
              'conversation_key': 'conv_v2_flutter',
              'symbol': '005930',
              'symbol_name': '삼성전자',
              'market': 'KR',
              'action': 'HOLD',
              'scores': {'final_score': 61},
              'confidence': 0.67,
              'analysis': {
                'action': 'HOLD',
                'risk_flags': ['final_score_gate_not_met'],
              },
              'requires_confirmation': false,
              'safety': {
                'real_order_submitted': false,
                'broker_submit_called': false,
              },
            },
    );
  }
}
