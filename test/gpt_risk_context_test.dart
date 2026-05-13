import 'package:flutter_test/flutter_test.dart';
import 'package:auto_invest_dashboard/models/gpt_risk_context.dart';

void main() {
  test('GptRiskContext parses full data safely', () {
    final context = GptRiskContext.fromJson({
      'market_risk_regime': 'risk_off',
      'technical_market_regime': 'trend',
      'event_risk_level': 'high',
      'fx_risk_level': 'medium',
      'geopolitical_risk_level': 'low',
      'energy_risk_level': 'medium',
      'political_regulatory_risk_level': 'low',
      'macro_risk_level': 'medium',
      'sector_fundamental_trend': 'mixed',
      'revenue_trend_context': 'stable',
      'flow_signal': 'negative',
      'earnings_revision_signal': 'neutral',
      'valuation_risk_level': 'medium',
      'entry_penalty': '6',
      'hard_block_new_buy': 'false',
      'allow_sell_or_exit': 'true',
      'gpt_buy_score': '58.5',
      'gpt_sell_score': 54,
      'affected_sectors': ['semiconductor'],
      'risk_flags': ['fx_pressure'],
      'gating_notes': ['entry penalty observed'],
      'reason': 'External risk is elevated.',
    });

    expect(context.marketRiskRegime, 'risk_off');
    expect(context.eventRiskLevel, 'high');
    expect(context.entryPenalty, 6);
    expect(context.hardBlockNewBuy, isFalse);
    expect(context.allowSellOrExit, isTrue);
    expect(context.gptBuyScore, 58.5);
    expect(context.gptSellScore, 54);
    expect(context.affectedSectors, ['semiconductor']);
    expect(context.riskFlags, ['fx_pressure']);
    expect(context.gatingNotes, ['entry penalty observed']);
    expect(context.hasDetails, isTrue);
  });

  test('GptRiskContext handles missing and null data', () {
    final missing = GptRiskContext.fromJson(null);
    final partial = GptRiskContext.fromJson({
      'hard_block_new_buy': null,
      'allow_sell_or_exit': null,
      'risk_flags': null,
      'gating_notes': null,
      'gpt_buy_score': 'not numeric',
    });

    expect(missing.hardBlockNewBuy, isFalse);
    expect(missing.allowSellOrExit, isTrue);
    expect(missing.riskFlags, isEmpty);
    expect(missing.gatingNotes, isEmpty);
    expect(missing.hasDetails, isFalse);

    expect(partial.hardBlockNewBuy, isFalse);
    expect(partial.allowSellOrExit, isTrue);
    expect(partial.gptBuyScore, isNull);
    expect(partial.riskFlags, isEmpty);
    expect(partial.gatingNotes, isEmpty);
  });
}
