import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/models/agent_chat_live_order_readiness.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';

void main() {
  test('refreshAgentChatLiveOrderReadiness loads readiness state', () async {
    final api = _ReadinessFakeApi();
    final controller = DashboardController(api, autoload: false);

    final result = await controller.refreshAgentChatLiveOrderReadiness();

    expect(result.success, isTrue);
    expect(api.readinessCalls, 1);
    expect(controller.agentChatLiveOrderReadiness?.ready, isFalse);
    expect(controller.isLoadingAgentChatLiveOrderReadiness, isFalse);
    expect(controller.agentChatLiveOrderSettingsError, isNull);

    controller.dispose();
  });

  test('applyAgentChatLiveOrderPreset calls preset endpoint only', () async {
    final api = _ReadinessFakeApi();
    final controller = DashboardController(api, autoload: false);

    final result =
        await controller.applyAgentChatLiveOrderPreset('chat_confirmed_buy_only');

    expect(result.success, isTrue);
    expect(result.message, contains('No order was submitted'));
    expect(api.presetCalls, 1);
    expect(api.lastPreset, 'chat_confirmed_buy_only');
    expect(api.readinessCalls, 0);
    expect(api.getOpsSettingsCalls, 1);
    expect(api.schedulerStatusCalls, 0);
    expect(api.manualSubmitCalls, 0);
    expect(api.validationCalls, 0);
    expect(controller.agentChatLiveOrderReadiness?.capabilities.buyEnabled,
        isTrue);
    expect(controller.applyingAgentChatLiveOrderPreset, isNull);

    controller.dispose();
  });
}

class _ReadinessFakeApi extends ApiClient {
  int readinessCalls = 0;
  int presetCalls = 0;
  int getOpsSettingsCalls = 0;
  int schedulerStatusCalls = 0;
  int manualSubmitCalls = 0;
  int validationCalls = 0;
  String? lastPreset;

  @override
  Future<AgentChatLiveOrderReadiness>
      fetchAgentChatLiveOrderReadiness() async {
    readinessCalls += 1;
    return _readiness(ready: false, buyEnabled: false);
  }

  @override
  Future<AgentChatLiveOrderSettingsApplyResult>
      applyAgentChatLiveOrderPreset(String preset) async {
    presetCalls += 1;
    lastPreset = preset;
    return AgentChatLiveOrderSettingsApplyResult.fromJson({
      'status': 'updated',
      'applied': true,
      'preset': preset,
      'changed_keys': ['agent_chat_live_order_buy_enabled'],
      'unchanged_keys': [],
      'audit_id': 77,
      'readiness': _readinessJson(ready: true, buyEnabled: true),
      'settings': {'agent_chat_live_order_buy_enabled': true},
      'safety': {
        'real_order_submitted': false,
        'broker_submit_called': false,
        'manual_submit_called': false,
        'validation_called': false,
        'scheduler_changed': false,
      },
      'warning_message': 'No order was submitted.',
    });
  }

  @override
  Future<OpsSettings> getOpsSettings() async {
    getOpsSettingsCalls += 1;
    return _safeOpsSettings();
  }
}

AgentChatLiveOrderReadiness _readiness({
  required bool ready,
  required bool buyEnabled,
}) {
  return AgentChatLiveOrderReadiness.fromJson(
    _readinessJson(ready: ready, buyEnabled: buyEnabled),
  );
}

Map<String, dynamic> _readinessJson({
  required bool ready,
  required bool buyEnabled,
}) {
  return {
    'status': ready ? 'ready' : 'blocked',
    'ready': ready,
    'ready_for_chat_confirmed_live_order': ready,
    'provider': 'kis',
    'market': 'KR',
    'summary': ready ? 'Ready.' : 'Blocked.',
    'checks': [
      {
        'key': 'dry_run',
        'label': 'Dry Run',
        'ok': ready,
        'value': !ready,
        'severity': ready ? 'ok' : 'blocking',
        'message': ready ? 'OK.' : 'dry_run is ON.',
      },
    ],
    'limits': {
      'max_orders_per_day': 1,
      'orders_used_today': 0,
      'orders_remaining_today': 1,
      'max_notional_krw': 50000,
      'max_notional_pct': 0.03,
    },
    'capabilities': {
      'buy_enabled': buyEnabled,
      'sell_enabled': false,
      'market_order_enabled': true,
      'limit_order_enabled': false,
    },
    'safety': {
      'read_only': true,
      'real_order_submitted': false,
      'validation_called': false,
      'scheduler_changed': false,
    },
  };
}

OpsSettings _safeOpsSettings() {
  return const OpsSettings(
    schedulerEnabled: false,
    botEnabled: false,
    dryRun: true,
    killSwitch: false,
    brokerMode: 'Paper',
    defaultGateLevel: 2,
    maxDailyTrades: 5,
    maxDailyEntries: 2,
    minEntryScore: 65,
    minScoreGap: 3,
  );
}
