import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/watchlist_section.dart';
import 'package:auto_invest_dashboard/models/kis_limited_auto_buy.dart';
import 'package:auto_invest_dashboard/models/kis_single_symbol_trading_result.dart';
import 'package:auto_invest_dashboard/models/managed_position.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';

void main() {
  testWidgets('KIS automation UI shows six simplified operator sections',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(find.byKey(const Key('kis_automation_main')), findsOneWidget);
    expect(
        find.byKey(const Key('kis_operations_readiness_card')), findsOneWidget);
    for (final label in [
      'Operations Readiness',
      'Watchlist Analyze & Buy',
      'Single Symbol Analyze & Buy',
      'Position Management',
      'Scheduled Position Management',
    ]) {
      expect(find.text(label), findsWidgets);
    }
    expect(
      find.textContaining(
        'KIS automation only places orders after all safety gates pass',
      ),
      findsOneWidget,
    );
    expect(find.text('Advanced Details'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('main KIS buttons are reduced and detailed cards are advanced',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    for (final label in [
      'Refresh Operations Readiness',
      'Analyze Watchlist & Buy',
      'Analyze Symbol & Buy',
      'Refresh Position Management',
      'Run Scheduled Management Check',
    ]) {
      expect(find.text(label), findsOneWidget);
    }
    expect(find.text('KIS Limited Buy Review'), findsNothing);
    expect(find.text('KIS Scheduler Guarded Sell Review'), findsNothing);

    await tester.tap(find.text('Advanced Details'));
    await tester.pumpAndSettle();

    expect(find.text('Advanced Buy Details'), findsOneWidget);
    expect(find.text('Advanced Scheduler Details'), findsOneWidget);
    expect(find.text('KIS Limited Buy Review'), findsOneWidget);
    expect(find.text('KIS Scheduler Guarded Sell Review'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('position management renders multi-position status',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller()
      ..kisManagedPositions = [
        ManagedPosition.fromJson(_positionJson(
          symbol: '005930',
          name: 'Samsung Electronics',
          status: 'SELL_READY',
          plPct: -0.09,
          stopLoss: true,
        )),
        ManagedPosition.fromJson(_positionJson(
          symbol: '035420',
          name: 'NAVER',
          status: 'HOLD',
          plPct: 0.04,
        )),
      ];

    await tester.pumpWidget(_wrap(controller));

    final card = find.byKey(const Key('kis_position_management_card'));
    expect(card, findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('HELD POSITIONS')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('MULTI-POSITION REVIEW')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('SELL READY')),
        findsWidgets);
    expect(
        find.descendant(
            of: card, matching: find.text('005930 / Samsung Electronics')),
        findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('035420 / NAVER')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('Prepare Manual Sell')),
        findsNothing);

    await tester.tap(find.descendant(
      of: card,
      matching: find.text('005930 / Samsung Electronics'),
    ));
    await tester.pumpAndSettle();

    expect(find.descendant(of: card, matching: find.text('Advanced action')),
        findsOneWidget);
    expect(
        find.descendant(of: card, matching: find.text('Prepare Manual Sell')),
        findsOneWidget);

    controller.dispose();
  });

  testWidgets('scheduled position management renders sell-before-buy messaging',
      (tester) async {
    await _setLargeView(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    final card =
        find.byKey(const Key('kis_scheduled_position_management_card'));
    expect(card, findsOneWidget);
    expect(find.descendant(of: card, matching: find.text('SELL REVIEW FIRST')),
        findsOneWidget);
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining(
          'Scheduled Position Management runs the position review first',
        ),
      ),
      findsOneWidget,
    );
    expect(
      find.descendant(
        of: card,
        matching: find.textContaining(
          'If a sell-ready position exists, new buy execution is skipped',
        ),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('raw payload remains collapsed in operator flow', (tester) async {
    await _setLargeView(tester);
    final controller = _controller()
      ..latestKisSingleSymbolTradingResult =
          KisSingleSymbolTradingResult.fromJson(_singleSymbolJson())
      ..latestKisLimitedAutoBuyResult =
          KisLimitedAutoBuy.fromJson(_limitedBuyJson());

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Developer Raw Payload'), findsOneWidget);
    expect(find.textContaining('"mode": "kis_single_symbol_analyze_buy"'),
        findsNothing);
    expect(find.text('KIS Limited Buy Review'), findsNothing);

    controller.dispose();
  });
}

Future<void> _setLargeView(WidgetTester tester) async {
  tester.view.physicalSize = const Size(1200, 9000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

DashboardController _controller() {
  return DashboardController(_FakeApiClient(), autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..selectedWatchlistMarket = PortfolioMarket.kr
    ..selectedPortfolioMarket = PortfolioMarket.kr
    ..krWatchlist = MarketWatchlist.fromJson({
      'market': 'KR',
      'currency': 'KRW',
      'timezone': 'Asia/Seoul',
      'watchlist_file': 'config/kis_watchlist.json',
      'symbols': [
        {'symbol': '005930', 'name': 'Samsung Electronics', 'market': 'KR'},
        {'symbol': '035420', 'name': 'NAVER', 'market': 'KR'},
      ],
    });
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(
      body: SingleChildScrollView(
        child: AnimatedBuilder(
          animation: controller,
          builder: (context, _) => KisAutomationSection(controller: controller),
        ),
      ),
    ),
  );
}

class _FakeApiClient extends ApiClient {}

Map<String, dynamic> _positionJson({
  required String symbol,
  required String name,
  required String status,
  required double plPct,
  bool stopLoss = false,
}) {
  return {
    'provider': 'kis',
    'market': 'KR',
    'symbol': symbol,
    'company_name': name,
    'quantity': 3,
    'average_price': 70000,
    'current_price': 65000,
    'current_value': 195000,
    'unrealized_pl': -15000,
    'unrealized_pl_pct': plPct,
    'holding_status': status,
    'exit_reason': stopLoss ? 'stop_loss_triggered' : 'no_exit_condition',
    'human_reason': stopLoss ? 'Stop-loss threshold reached' : 'Hold.',
    'stop_loss_triggered': stopLoss,
    'take_profit_triggered': false,
    'weak_trend_triggered': false,
    'sell_pressure_triggered': false,
    'manual_review_required': status != 'HOLD',
    'final_sell_score': stopLoss ? 82 : 35,
    'technical_snapshot': {},
    'risk_flags': [],
    'gating_notes': [],
    'block_reasons': [],
    'can_prepare_manual_sell': status != 'HOLD',
    'can_submit_manual_sell': false,
  };
}

Map<String, dynamic> _singleSymbolJson() {
  return {
    'status': 'ok',
    'mode': 'kis_single_symbol_analyze_buy',
    'provider': 'kis',
    'market': 'KR',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'score_below_threshold',
    'symbol': '005930',
    'requested_symbol': '005930',
    'analyzed_symbol': '005930',
    'returned_symbol': '005930',
    'symbol_match': true,
    'quantity': 1,
    'final_buy_score': 62,
    'effective_min_entry_score': 75,
    'indicator_status': 'ok',
    'indicator_bar_count': 120,
    'estimated_order_amount': 75000,
    'available_cash': 200000,
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'dry_run': true,
  };
}

Map<String, dynamic> _limitedBuyJson() {
  return {
    'status': 'ok',
    'mode': 'kis_limited_auto_buy_run',
    'result': 'blocked',
    'action': 'hold',
    'reason': 'scheduler_real_orders_disabled',
    'real_order_submitted': false,
    'broker_submit_called': false,
    'manual_submit_called': false,
    'validation_called': false,
    'final_candidate': {
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'status': 'HOLD',
      'final_buy_score': 71,
      'required_buy_score': 75,
      'cash_sufficient': true,
      'duplicate_position': false,
      'duplicate_open_buy_order': false,
      'entry_ready': false,
    },
  };
}
