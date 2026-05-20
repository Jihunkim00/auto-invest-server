import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/managed_position.dart';

void main() {
  test('managed position parses company name and sell-ready detail', () {
    final position = ManagedPosition.fromJson({
      'provider': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'quantity': 2,
      'current_price': 72000,
      'current_value': 144000,
      'unrealized_pl': -3000,
      'unrealized_pl_pct': -0.02,
      'holding_status': 'SELL_READY',
      'exit_reason': 'stop_loss_triggered',
      'human_reason': 'Stop-loss threshold reached.',
      'stop_loss_triggered': true,
      'technical_snapshot': {
        'ema20': 73000,
        'price_vs_ema20': 'below',
        'rsi': 32,
      },
      'risk_flags': ['stop_loss_triggered'],
      'gating_notes': ['Manual sell must use existing submit path.'],
      'block_reasons': ['runtime_dry_run_enabled'],
      'can_prepare_manual_sell': true,
      'can_submit_manual_sell': false,
    });

    expect(position.symbol, '005930');
    expect(position.companyName, 'Samsung Electronics');
    expect(position.statusLabel, 'SELL READY');
    expect(position.isSellReady, isTrue);
    expect(position.stopLossTriggered, isTrue);
    expect(position.technicalSnapshot['price_vs_ema20'], 'below');
    expect(position.blockReasons, contains('runtime_dry_run_enabled'));
  });

  test('managed position falls back when company name is missing', () {
    final position = ManagedPosition.fromJson({
      'symbol': '091810',
      'quantity': 10,
      'holding_status': 'REVIEW_SELL',
    });

    expect(position.companyName, 'Unknown company');
    expect(position.statusLabel, 'REVIEW SELL');
  });

  test('manual sell preparation preserves portfolio source metadata', () {
    final preparation = ManualSellPreparation.fromJson({
      'provider': 'kis',
      'market': 'KR',
      'symbol': '005930',
      'company_name': 'Samsung Electronics',
      'suggested_quantity': 2,
      'estimated_amount': 144000,
      'exit_reason': 'weak_trend_triggered',
      'human_reason': 'Weak trend detected.',
      'holding_status': 'REVIEW_SELL',
      'can_prepare': true,
      'can_submit': false,
      'block_reasons': ['runtime_dry_run_enabled'],
      'source_metadata': {
        'source': 'kis_portfolio_manual_sell',
        'source_type': 'operator_confirmed_position_exit',
      },
    });

    expect(preparation.companyName, 'Samsung Electronics');
    expect(preparation.quantity, 2);
    expect(preparation.sourceMetadata['source'], 'kis_portfolio_manual_sell');
    expect(preparation.blockReasons, contains('runtime_dry_run_enabled'));
  });
}
