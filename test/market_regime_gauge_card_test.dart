import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/theme/app_theme.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/home/home_screen.dart';
import 'package:auto_invest_dashboard/features/home/widgets/market_regime_gauge_card.dart';
import 'package:auto_invest_dashboard/models/market_regime.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('KIS selection displays the gauge and Alpaca does not',
      (tester) async {
    final kis = DashboardController(ApiClient(), autoload: false)
      ..marketRegime = _regime(2);
    await tester.pumpWidget(_home(kis));
    expect(find.byKey(const ValueKey('home-market-regime-gauge-card')),
        findsOneWidget);
    kis.dispose();

    final alpaca = DashboardController(ApiClient(), autoload: false)
      ..selectedProvider = SelectedProvider.alpaca
      ..marketRegime = _regime(2);
    await tester.pumpWidget(_home(alpaca));
    expect(find.byKey(const ValueKey('home-market-regime-gauge-card')),
        findsNothing);
    alpaca.dispose();
  });

  testWidgets('all six cycle positions show their matching stage text',
      (tester) async {
    const labels = ['하락', '바닥 탐색', '상승 전환', '상승', '상승 둔화', '하락 전환'];
    for (var stage = 1; stage <= 6; stage++) {
      await tester.pumpWidget(_app(
        MarketRegimeGaugeCard(regime: _regime(stage)),
      ));
      expect(
        find.text(stage.toString() + '단계 · ' + labels[stage - 1]),
        findsOneWidget,
      );
    }
  });

  testWidgets('pending and insufficient-data states render safely',
      (tester) async {
    final pending = MarketRegime.fromJson({'status': 'pending'});
    await tester.pumpWidget(_app(MarketRegimeGaugeCard(regime: pending)));
    expect(find.text('확정 대기'), findsOneWidget);

    final insufficient = MarketRegime.fromJson({'status': 'insufficient_data'});
    await tester.pumpWidget(_app(MarketRegimeGaugeCard(regime: insufficient)));
    expect(find.text('확정 보류'), findsOneWidget);
  });

  testWidgets('loading and API error states remain compact', (tester) async {
    await tester.pumpWidget(_app(const MarketRegimeGaugeCard(
      regime: null,
      loading: true,
    )));
    expect(find.text('계산 중'), findsOneWidget);

    await tester.pumpWidget(_app(const MarketRegimeGaugeCard(
      regime: null,
      error: 'unavailable',
    )));
    expect(find.text('현재 지표를 불러올 수 없음'), findsOneWidget);
  });

  testWidgets('tapping the gauge opens details with API values unchanged',
      (tester) async {
    await tester.pumpWidget(_app(MarketRegimeGaugeCard(regime: _regime(2))));
    await tester
        .tap(find.byKey(const ValueKey('home-market-regime-gauge-tap')));
    await tester.pumpAndSettle();

    final sheet = find.byKey(const ValueKey('home-market-regime-detail-sheet'));
    expect(sheet, findsOneWidget);
    expect(find.textContaining('KOSPI 60% + NASDAQ 40%'), findsOneWidget);
    for (final value in ['61.23', '56.70', '67.37', '+5.7']) {
      expect(
        find.descendant(of: sheet, matching: find.text(value)),
        findsOneWidget,
      );
    }
  });
}

MarketRegime _regime(int stage) {
  const labels = ['하락', '바닥 탐색', '상승 전환', '상승', '상승 둔화', '하락 전환'];
  const fullLabels = [
    '하락 진행',
    '하락 둔화·바닥 탐색',
    '상승 전환 확인',
    '상승 진행',
    '상승 둔화·고점권',
    '하락 전환 확인',
  ];
  return MarketRegime.fromJson({
    'status': 'confirmed',
    'stage': stage,
    'stage_label': fullLabels[stage - 1],
    'short_label': labels[stage - 1],
    'summary': '주간 요약',
    'market_score': 61.23,
    'score_change_3w': 5.73,
    'kospi_score': 56.70,
    'nasdaq_score': 67.37,
    'confirmed': true,
    'kospi': {'drawdown_52w': 4.25},
    'bullish_transition': {
      'conditions': [
        {'key': 'one', 'label': '시장 점수 >= 60', 'passed': true},
      ],
    },
  });
}

Widget _app(Widget child) => MaterialApp(
      theme: AppTheme.darkTheme,
      home: Scaffold(body: SingleChildScrollView(child: child)),
    );

Widget _home(DashboardController controller) => MaterialApp(
      theme: AppTheme.darkTheme,
      home: HomeScreen(controller: controller),
    );
