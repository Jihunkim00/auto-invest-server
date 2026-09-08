import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/utils/kr_stock_catalog.dart';
import 'package:auto_invest_dashboard/features/ai/ai_screen.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_v2_response.dart';
import 'package:auto_invest_dashboard/models/automation_strategy_profile.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    await KrStockCatalog.shared.load();
  });

  testWidgets('AI quick action renders analysis card from V2 response',
      (tester) async {
    final api = _FakeV2Api();
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(
      MaterialApp(home: AiScreen(controller: controller)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const ValueKey('ai-quick-종목 분석')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(api.messages, hasLength(1));
    expect(api.messages.single, startsWith('삼성전자 분석해줘'));
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
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

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

    expect(find.byType(ActionChip), findsNothing);
    expect(find.byType(OutlinedButton), findsNWidgets(5));
    for (var index = 0; index < 5; index++) {
      expect(
        tester.getSize(find.byType(OutlinedButton).at(index)).height,
        greaterThanOrEqualTo(46),
      );
    }
    await tester.enterText(
      find.byKey(const ValueKey('ai-v2-input')),
      '삼성전자 최근 실적과 위험 요인을 자세히 설명해 주세요. '
      '긴 한국어 질문도 화면 밖으로 잘리지 않아야 합니다.',
    );
    await tester.tap(find.byKey(const ValueKey('ai-v2-send')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    final userMessage = find.byKey(const ValueKey('ai-v2-user-message'));
    expect(userMessage, findsOneWidget);
    expect(tester.getSize(userMessage).width, lessThanOrEqualTo(398));
    expect(find.byKey(const ValueKey('ai-v2-analysis-card')), findsOneWidget);
    expect(tester.takeException(), isNull);
    controller.dispose();
  });

  testWidgets('AI resolves catalog Korean names outside the active watchlist',
      (tester) async {
    final api = _FakeV2Api(
      kisPrices: {
        '000660': {
          'symbol': '000660',
          'current_price': 123456,
          'timestamp': '2026-09-08T13:30:00+09:00',
        },
      },
    );
    final controller = DashboardController(api, autoload: false)
      ..krWatchlist = MarketWatchlist.empty('KR');

    await tester
        .pumpWidget(MaterialApp(home: AiScreen(controller: controller)));
    await tester.enterText(
      find.byKey(const ValueKey('ai-v2-input')),
      'SK하이닉스 현재가 알려줘',
    );
    await tester.tap(find.byKey(const ValueKey('ai-v2-send')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(api.priceSymbols, ['000660']);
    expect(api.messages, isEmpty);
    expect(find.byKey(const ValueKey('ai-local-quote-card')), findsOneWidget);
    expect(find.textContaining('SK'), findsWidgets);
    expect(find.textContaining('(000660)'), findsWidgets);
    expect(find.textContaining('123,456'), findsOneWidget);
    controller.dispose();
  });

  testWidgets('AI routes Hyundai Construction quotes through KIS directly',
      (tester) async {
    final api = _FakeV2Api(
      kisPrices: {
        '000720': {'symbol': '000720', 'current_price': 70000},
      },
    );
    final controller = DashboardController(api, autoload: false)
      ..krWatchlist = MarketWatchlist.fromJson({
        'market': 'KR',
        'symbols': [
          {'symbol': '000720', 'name': '현대건설'},
        ],
      });

    await tester
        .pumpWidget(MaterialApp(home: AiScreen(controller: controller)));
    await tester.enterText(
      find.byKey(const ValueKey('ai-v2-input')),
      '현대건설 가격 알려줘',
    );
    await tester.tap(find.byKey(const ValueKey('ai-v2-send')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(api.priceSymbols, ['000720']);
    expect(api.messages, isEmpty);
    expect(find.textContaining('(000720)'), findsWidgets);
    controller.dispose();
  });

  testWidgets('AI answers read-only automation profile lookup locally',
      (tester) async {
    final api = _FakeV2Api(automationProfiles: true);
    final controller = DashboardController(api, autoload: false);

    await tester
        .pumpWidget(MaterialApp(home: AiScreen(controller: controller)));
    await tester.enterText(
      find.byKey(const ValueKey('ai-v2-input')),
      '현재 자동화 프로필 상태 알려줘',
    );
    await tester.tap(find.byKey(const ValueKey('ai-v2-send')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byKey(const ValueKey('ai-local-assistant-message')),
        findsOneWidget);
    expect(find.textContaining('demo profile'), findsOneWidget);
    expect(api.profileCalls, 1);
    expect(api.messages, isEmpty);
    controller.dispose();
  });
}

class _FakeV2Api extends ApiClient {
  _FakeV2Api({
    this.tradePrepare = false,
    this.automationProfiles = false,
    this.kisPrices = const {},
  });

  final bool tradePrepare;
  final bool automationProfiles;
  final Map<String, Map<String, dynamic>> kisPrices;
  final List<String> messages = [];
  final List<Map<String, dynamic>> contexts = [];
  final List<String> priceSymbols = [];
  int profileCalls = 0;

  @override
  Future<Map<String, dynamic>> fetchKisMarketPrice(String symbol) async {
    priceSymbols.add(symbol);
    final result = kisPrices[symbol];
    if (result == null) throw const ApiRequestException('missing quote');
    return Map<String, dynamic>.from(result);
  }

  @override
  Future<AutomationStrategyProfileList> fetchAutomationProfiles() async {
    profileCalls += 1;
    if (!automationProfiles) throw const ApiRequestException('not configured');
    return AutomationStrategyProfileList.fromJson({
      'profiles': [
        {
          'id': 1,
          'profile_key': 'demo',
          'name': 'demo profile',
          'provider': 'kis',
          'market': 'KR',
          'status': 'active',
          'enabled': true,
          'settings': {
            'max_open_positions': 2,
            'entry': {
              'analysis_times': ['09:30', '13:30'],
              'max_new_entries_per_day': 1,
            },
            'operation': {
              'start_date': '2026-09-01',
              'end_date': '2026-09-30',
            },
          },
        },
      ],
    });
  }

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
    contexts.add(Map<String, dynamic>.from(context ?? const {}));
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
