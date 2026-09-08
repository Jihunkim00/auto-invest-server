import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/core/utils/kr_stock_catalog.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/home_latest_ai_decision_card.dart';
import 'package:auto_invest_dashboard/models/market_watchlist.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';
import 'package:auto_invest_dashboard/models/watchlist_run_result.dart';

void main() {
  testWidgets('Home detail resolves a known KR symbol from the catalog',
      (tester) async {
    await KrStockCatalog.shared.load();
    final controller = DashboardController(ApiClient(), autoload: false)
      ..runResult = WatchlistRunResult.fromJson({
        'final_ranked_candidates': [
          {'symbol': '005930', 'final_entry_score': 72},
        ],
      });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: HomeLatestAiDecisionCard(controller: controller),
        ),
      ),
    );
    await tester.tap(
      find.byKey(const ValueKey('home-latest-ai-decision-card-surface')),
    );
    await tester.pumpAndSettle();

    expect(find.text('삼성전자 (005930)'), findsWidgets);
    controller.dispose();
  });

  testWidgets('Home latest AI card stays compact and opens GPT detail',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..krWatchlist = MarketWatchlist.fromJson({
        'market': 'KR',
        'symbols': [
          {'symbol': '267250', 'name': 'HD현대일렉트릭'},
        ],
      })
      ..runResult = _runResult()
      ..schedulerStatus = _schedulerStatus();

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: HomeLatestAiDecisionCard(controller: controller),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final card =
        find.byKey(const ValueKey('home-latest-ai-decision-card-surface'));
    expect(card, findsOneWidget);
    expect(tester.getSize(card).height, lessThan(180));

    await tester.tap(card);
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey('home-ai-decision-detail-dialog')),
        findsOneWidget);
    expect(find.text('HD현대일렉트릭 (267250)'), findsWidgets);
    expect(find.textContaining('GPT 79'), findsWidgets);
    expect(find.textContaining('Quant 61.8'), findsWidgets);
    expect(find.textContaining('Final 62'), findsWidgets);
    expect(find.byKey(const ValueKey('home-ai-slot-09:30')), findsOneWidget);
    expect(find.textContaining('프로필 최소 매수 점수 미달'), findsWidgets);

    await tester.tap(find.byKey(const ValueKey('home-ai-detail-close')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('home-ai-decision-detail-dialog')),
        findsNothing);
    controller.dispose();
  });

  testWidgets('Home detail uses the requested fallback for an unknown stock',
      (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..runResult = WatchlistRunResult.fromJson({
        'final_ranked_candidates': [
          {'symbol': '123456', 'final_entry_score': 62},
        ],
      });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: HomeLatestAiDecisionCard(controller: controller)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('종목명 미확인 (123456)'), findsOneWidget);
    controller.dispose();
  });

  testWidgets('Home detail keeps US tickers unchanged', (tester) async {
    final controller = DashboardController(ApiClient(), autoload: false)
      ..selectedProvider = SelectedProvider.alpaca
      ..runResult = WatchlistRunResult.fromJson({
        'final_ranked_candidates': [
          {'symbol': 'AAPL', 'name': 'Apple', 'final_entry_score': 72},
        ],
      });

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: HomeLatestAiDecisionCard(controller: controller),
        ),
      ),
    );
    await tester.tap(
      find.byKey(const ValueKey('home-latest-ai-decision-card-surface')),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('AAPL'), findsWidgets);
    expect(find.textContaining('삼성전자'), findsNothing);
    controller.dispose();
  });
}

WatchlistRunResult _runResult() {
  return WatchlistRunResult.fromJson({
    'final_ranked_candidates': [
      {
        'symbol': '267250',
        'company_name': 'HD현대일렉트릭',
        'gpt_buy_score': 79,
        'quant_score': 61.8,
        'final_entry_score': 62,
        'reason': '추세와 거래량을 확인하지만 프로필 기준 미달',
        'block_reason': 'below_profile_buy_threshold',
      },
    ],
    'trigger_block_reason': 'below_profile_buy_threshold',
    'reason': 'below_profile_buy_threshold',
  });
}

SchedulerStatus _schedulerStatus() {
  return const SchedulerStatus(
    runtimeSchedulerEnabled: false,
    us: MarketSchedulerStatus(
      enabledForScheduler: false,
      timezone: 'America/New_York',
      slots: [],
    ),
    kr: MarketSchedulerStatus(
      enabledForScheduler: false,
      timezone: 'Asia/Seoul',
      slots: [],
    ),
    profileAnalysisTimes: ['09:30', '12:00', '13:30'],
    lastProfileRunAt: '2026-09-08T13:30:00+09:00',
  );
}
