import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_send_response.dart';
import 'package:auto_invest_dashboard/models/strategy_performance.dart';

import 'strategy_performance_fixtures.dart';

void main() {
  test('strategy performance models parse API payloads', () {
    final daily =
        StrategyDailyPerformance.fromJson(strategyDailyPerformanceJson());
    final monthly =
        StrategyMonthlyPerformance.fromJson(strategyMonthlyPerformanceJson());
    final trades =
        StrategyTradePerformanceList.fromJson(strategyTradePerformanceJson());

    expect(daily.netPnlEstimated, 9500);
    expect(daily.dataQuality.hasWarnings, isFalse);
    expect(monthly.targetProgressPct, 66.7);
    expect(monthly.newEntriesAllowedByTarget, isTrue);
    expect(monthly.profitFactor, 7.0);
    expect(trades.count, 1);
    expect(trades.items.single.entryOrderId, 10);
    expect(trades.items.single.displayPnl, 4000);
  });

  test('performance intents are read only in Flutter', () {
    for (final category in [
      'strategy_daily_performance_query',
      'strategy_monthly_performance_query',
      'strategy_target_progress_query',
      'strategy_trade_performance_query',
      'strategy_loss_budget_query',
    ]) {
      final response = AgentChatSendResponse.fromJson({
        'conversation_key': 'performance',
        'intent': {
          'category': category,
          'supported': true,
          'confidence': 1,
          'side': 'none',
          'requires_plan': false,
          'requires_auth': false,
          'requires_manual_confirmation': false,
          'fallback_used': false,
          'parser_status': 'rule',
        },
        'answer': {
          'role': 'assistant',
          'text': 'Read-only performance answer',
          'answer_type': 'strategy_performance_answer',
        },
        'data': const {},
        'safety': strategySafetyJson(),
      });

      expect(response.intent.isReadOnly, isTrue, reason: category);
    }
  });
}
