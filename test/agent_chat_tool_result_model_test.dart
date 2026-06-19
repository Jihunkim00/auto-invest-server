import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/models/agent_chat_tool_result.dart';

void main() {
  test('AgentChatToolResult parses safety and result payload', () {
    final result = AgentChatToolResult.fromJson({
      'tool_name': 'kis_price_lookup',
      'status': 'success',
      'result_type': 'price',
      'data': {
        'price': {'symbol': '005930', 'price': 72000},
      },
      'summary': 'ok',
      'safety': {
        'read_only': true,
        'mutation': false,
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'setting_changed': false,
        'scheduler_changed': false,
        'confirm_live_auto_checked': false,
      },
    });

    expect(result.toolName, 'kis_price_lookup');
    expect(result.isSuccess, isTrue);
    expect(result.data['price']['price'], 72000);
    expect(result.safety.readOnly, isTrue);
    expect(result.safety.realOrderSubmitted, isFalse);
  });

  test('AgentChatResultCard parses rows and badges', () {
    final card = AgentChatResultCard.fromJson({
      'card_type': 'settings',
      'title': 'System Status',
      'badges': ['READ ONLY', 'NO SETTINGS CHANGE'],
      'rows': [
        {'label': 'dry_run', 'value': 'ON'},
      ],
      'data': {'dry_run': true},
    });

    expect(card.cardType, 'settings');
    expect(card.title, 'System Status');
    expect(card.badges, contains('NO SETTINGS CHANGE'));
    expect(card.rows.first['label'], 'dry_run');
    expect(card.data['dry_run'], isTrue);
  });
}
