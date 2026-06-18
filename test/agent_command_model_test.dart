import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_command.dart';

void main() {
  test('Agent command parse result preserves parser metadata', () {
    final result = AgentCommandParseResult.fromJson({
      'status': 'parsed',
      'parser_status': 'failed_fallback_used',
      'model_name': 'gpt-5.4-mini',
      'command_log_id': 42,
      'command': {
        'schema_version': 'autoinvest_command_v1',
        'command_type': 'RUN_SINGLE_SYMBOL_ANALYSIS',
        'domain': 'analysis',
        'intent': 'single_symbol_analysis',
        'market': 'KR',
        'provider': 'kis',
        'symbol': '005930',
        'side': 'none',
        'risk_level': 'analysis_only',
        'requires_auth': false,
        'user_visible_summary': 'Analyze Samsung.',
        'parser_confidence': 0.91,
        'execution_policy': {'allow_live_order': false},
        'safety': {'real_order_submitted': false},
      },
      'safety': {'real_order_submitted': false},
    });

    expect(result.commandLogId, 42);
    expect(result.fallbackUsed, isTrue);
    expect(result.modelName, 'gpt-5.4-mini');
    expect(result.command.commandType, 'RUN_SINGLE_SYMBOL_ANALYSIS');
    expect(result.command.symbol, '005930');
    expect(result.command.requiresAuth, isFalse);
    expect(result.command.executionPolicy['allow_live_order'], isFalse);
  });
}
