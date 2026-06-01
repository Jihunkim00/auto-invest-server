import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/settings/settings_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_buy.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';

void main() {
  testWidgets('dry-run switch success persists and refreshes settings',
      (tester) async {
    final api = _SettingsFakeApiClient(refreshedDryRun: false);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(controller));

    expect(_dryRunTile(tester).value, isTrue);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Dry Run'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate, {'dry_run': false});
    expect(api.getOpsSettingsCalls, 1);
    expect(controller.settings.dryRun, isFalse);
    expect(_dryRunTile(tester).value, isFalse);
    expect(
      find.descendant(
        of: find.byType(SnackBar),
        matching: find.text('Dry run disabled successfully.'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('dry-run switch failure rolls back and refreshes settings',
      (tester) async {
    final api = _SettingsFakeApiClient(throwUpdateOpsSettings: true);
    final controller = DashboardController(api, autoload: false);

    await tester.pumpWidget(_wrap(controller));

    expect(_dryRunTile(tester).value, isTrue);

    await tester.tap(find.widgetWithText(SwitchListTile, 'Dry Run'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate, {'dry_run': false});
    expect(api.getOpsSettingsCalls, 1);
    expect(controller.settings.dryRun, isTrue);
    expect(_dryRunTile(tester).value, isTrue);
    expect(
      find.descendant(
        of: find.byType(SnackBar),
        matching: find.textContaining('Dry run update failed:'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('KIS settings expose editable automation controls',
      (tester) async {
    _useTallSettingsViewport(tester);
    final controller =
        DashboardController(_SettingsFakeApiClient(), autoload: false)
          ..selectedProvider = SelectedProvider.kis
          ..settings = _opsSettings();

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('KIS Automation Controls'), findsWidgets);
    expect(find.widgetWithText(SwitchListTile, 'KIS Scheduler Enabled'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'KIS Scheduler Dry Run'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'KIS Scheduler Real Orders'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'KIS Scheduler Sell Enabled'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'KIS Scheduler Buy Enabled'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'KIS Live Auto Sell'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'KIS Live Auto Buy'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'Stop-loss Auto Sell'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'Take-profit Auto Sell'),
        findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'Limited Auto Buy'),
        findsOneWidget);
    expect(
        find.widgetWithText(
            SwitchListTile, 'Limited Auto Buy Shadow Review Required'),
        findsOneWidget);
    expect(
        find.widgetWithText(
            SwitchListTile, 'Scheduler Allow Limited Auto Sell'),
        findsOneWidget);
    expect(
        find.widgetWithText(SwitchListTile, 'Scheduler Allow Limited Auto Buy'),
        findsOneWidget);
    expect(find.text('KIS Runtime Diagnostics'), findsWidgets);
    expect(find.widgetWithText(SwitchListTile, 'Dry Run'), findsOneWidget);
    expect(find.widgetWithText(SwitchListTile, 'Kill Switch'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('dangerous KIS ON toggle confirms before API call',
      (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..settings = _opsSettings();

    await tester.pumpWidget(_wrap(controller));

    await tester
        .tap(find.widgetWithText(SwitchListTile, 'KIS Scheduler Real Orders'));
    await tester.pumpAndSettle();

    expect(find.text('KIS Scheduler Real Orders'), findsWidgets);
    expect(
      find.textContaining(
          'This may allow real KIS orders when all backend gates pass.'),
      findsOneWidget,
    );
    expect(api.updateOpsSettingsCalls, 0);

    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 0);
    expect(controller.settings.kisSchedulerAllowRealOrders, isFalse);

    controller.dispose();
  });

  testWidgets('confirmed KIS ON toggle sends expected settings field',
      (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..settings = _opsSettings();

    await tester.pumpWidget(_wrap(controller));

    await tester.tap(find.widgetWithText(SwitchListTile, 'KIS Live Auto Sell'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate, {'kis_live_auto_sell_enabled': true});
    expect(api.getOpsSettingsCalls, 1);
    expect(api.schedulerStatusCalls, 1);
    expect(api.guardedSellStatusCalls, 1);
    expect(api.guardedBuyStatusCalls, 1);

    controller.dispose();
  });

  testWidgets('KIS automation failure rolls back and refreshes settings',
      (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient(throwUpdateOpsSettings: true);
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..settings = _opsSettings();

    await tester.pumpWidget(_wrap(controller));

    await tester.tap(find.widgetWithText(SwitchListTile, 'KIS Live Auto Sell'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.getOpsSettingsCalls, 1);
    expect(controller.settings.kisLiveAutoSellEnabled, isFalse);
    expect(
      tester
          .widget<SwitchListTile>(
              find.widgetWithText(SwitchListTile, 'KIS Live Auto Sell'))
          .value,
      isFalse,
    );
    expect(
      find.descendant(
        of: find.byType(SnackBar),
        matching: find.textContaining('KIS Live Auto Sell update failed:'),
      ),
      findsOneWidget,
    );

    controller.dispose();
  });

  testWidgets('Safe Mode preset sends safe payload', (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..settings = _opsSettings(
        dryRun: false,
        kisSchedulerEnabled: true,
        kisSchedulerAllowRealOrders: true,
        kisSchedulerConfiguredAllowRealOrders: true,
        kisLiveAutoSellEnabled: true,
        kisLiveAutoBuyEnabled: true,
      );

    await tester.pumpWidget(_wrap(controller));

    await tester.tap(find.text('Return to Safe Mode'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate?['dry_run'], isTrue);
    expect(api.lastSettingsUpdate?['kill_switch'], isFalse);
    expect(api.lastSettingsUpdate?['kis_scheduler_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_scheduler_dry_run'], isTrue);
    expect(api.lastSettingsUpdate?['kis_scheduler_live_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_scheduler_allow_real_orders'], isFalse);
    expect(api.lastSettingsUpdate?['kis_live_auto_sell_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_live_auto_buy_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_limited_auto_sell_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_limited_auto_buy_enabled'], isFalse);
    expect(find.text('Settings Change Result'), findsOneWidget);
    expect(find.text('Safe Mode enabled'), findsOneWidget);
    expect(find.text('KIS Scheduler Effective OFF'), findsOneWidget);
    expect(find.text('KIS Real Order Scheduler OFF'), findsOneWidget);
    expect(find.text('KIS Sell OFF'), findsOneWidget);
    expect(find.text('KIS Buy OFF'), findsOneWidget);
    expect(find.text('Dry Run ON'), findsOneWidget);
    expect(find.text('Kill Switch OFF'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Sell-only Test Mode preset keeps buy flags false',
      (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient();
    final controller = DashboardController(api, autoload: false)
      ..selectedProvider = SelectedProvider.kis
      ..settings = _opsSettings();

    await tester.pumpWidget(_wrap(controller));

    await tester.tap(find.text('Enable KIS Sell-Only Test Mode'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate?['dry_run'], isFalse);
    expect(api.lastSettingsUpdate?['kill_switch'], isFalse);
    expect(api.lastSettingsUpdate?['scheduler_enabled'], isTrue);
    expect(api.lastSettingsUpdate?['kis_scheduler_enabled'], isTrue);
    expect(api.lastSettingsUpdate?['kis_scheduler_dry_run'], isFalse);
    expect(api.lastSettingsUpdate?['kis_scheduler_live_enabled'], isTrue);
    expect(api.lastSettingsUpdate?['kis_scheduler_allow_real_orders'], isTrue);
    expect(api.lastSettingsUpdate?['kis_scheduler_sell_enabled'], isTrue);
    expect(api.lastSettingsUpdate?['kis_live_auto_sell_enabled'], isTrue);
    expect(
        api.lastSettingsUpdate?['kis_limited_auto_stop_loss_enabled'], isTrue);
    expect(api.lastSettingsUpdate?['kis_limited_auto_take_profit_enabled'],
        isTrue);
    expect(api.lastSettingsUpdate?['kis_scheduler_buy_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_live_auto_buy_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_limited_auto_buy_enabled'], isFalse);
    expect(api.lastSettingsUpdate?['kis_scheduler_allow_limited_auto_buy'],
        isFalse);
    expect(api.lastSettingsUpdate?['kis_scheduler_allow_limited_auto_sell'],
        isTrue);
    expect(find.text('Settings Change Result'), findsOneWidget);
    expect(find.text('Sell-Only Test Mode enabled'), findsOneWidget);
    expect(find.text('KIS Scheduler Effective ON'), findsOneWidget);
    expect(find.text('KIS Real Order Scheduler ON'), findsOneWidget);
    expect(find.text('KIS Sell ON'), findsOneWidget);
    expect(find.text('KIS Buy OFF'), findsOneWidget);
    expect(find.text('Dry Run OFF'), findsOneWidget);
    expect(find.text('Kill Switch OFF'), findsOneWidget);

    controller.dispose();
  });
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: SettingsScreen(controller: controller)),
  );
}

void _useTallSettingsViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 3200);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

SwitchListTile _dryRunTile(WidgetTester tester) {
  return tester.widget<SwitchListTile>(
    find.widgetWithText(SwitchListTile, 'Dry Run'),
  );
}

class _SettingsFakeApiClient extends ApiClient {
  _SettingsFakeApiClient({
    this.refreshedDryRun = true,
    this.throwUpdateOpsSettings = false,
    OpsSettings? initialSettings,
  }) : currentSettings =
            initialSettings ?? _opsSettings(dryRun: refreshedDryRun);

  final bool refreshedDryRun;
  final bool throwUpdateOpsSettings;
  OpsSettings currentSettings;
  int getOpsSettingsCalls = 0;
  int updateOpsSettingsCalls = 0;
  int schedulerStatusCalls = 0;
  int guardedSellStatusCalls = 0;
  int guardedBuyStatusCalls = 0;
  Map<String, dynamic>? lastSettingsUpdate;

  @override
  Future<OpsSettings> getOpsSettings() async {
    getOpsSettingsCalls += 1;
    return currentSettings;
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    updateOpsSettingsCalls += 1;
    lastSettingsUpdate = Map<String, dynamic>.from(values);
    if (throwUpdateOpsSettings) {
      throw const ApiRequestException(
        'HTTP 500: {"message":"settings failed"}',
      );
    }
    currentSettings = _settingsWithPayload(currentSettings, values);
  }

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    return KisManualOrderSafetyStatus(
      runtimeDryRun: currentSettings.dryRun,
      killSwitch: currentSettings.killSwitch,
      kisEnabled: true,
      kisRealOrderEnabled: true,
      marketOpen: true,
      entryAllowedNow: true,
      noNewEntryAfter: '15:00',
    );
  }

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async {
    schedulerStatusCalls += 1;
    final effective = currentSettings.schedulerEnabled &&
        currentSettings.kisSchedulerEnabled &&
        (currentSettings.kisSchedulerDryRun ||
            (currentSettings.kisSchedulerLiveEnabled &&
                currentSettings.kisSchedulerAllowRealOrders &&
                currentSettings.kisSchedulerConfiguredAllowRealOrders &&
                currentSettings.kisSchedulerAllowLimitedAutoSell &&
                !currentSettings.dryRun &&
                !currentSettings.killSwitch));
    final realOrder = effective &&
        currentSettings.kisSchedulerLiveEnabled &&
        currentSettings.kisSchedulerAllowRealOrders &&
        currentSettings.kisSchedulerConfiguredAllowRealOrders &&
        currentSettings.kisSchedulerAllowLimitedAutoSell &&
        !currentSettings.kisSchedulerDryRun &&
        !currentSettings.dryRun &&
        !currentSettings.killSwitch;
    return SchedulerStatus(
      runtimeSchedulerEnabled: currentSettings.schedulerEnabled,
      us: const MarketSchedulerStatus(
        enabledForScheduler: true,
        timezone: 'America/New_York',
        slots: ['midday 12:00'],
      ),
      kr: MarketSchedulerStatus(
        enabledForScheduler: effective,
        timezone: 'Asia/Seoul',
        slots: const ['midday 11:30'],
        realOrdersAllowed: realOrder,
        realOrderSchedulerEnabled: realOrder,
        liveSchedulerReady: realOrder,
        krSchedulerAnyEnabled: effective,
        krLiveSchedulerEnabledEffective: realOrder,
        krDryRunSchedulerEnabledEffective:
            effective && currentSettings.kisSchedulerDryRun,
        enabledForSchedulerBlockReasons:
            effective ? const [] : const ['kis_scheduler_disabled'],
      ),
    );
  }

  @override
  Future<KisSchedulerGuardedSellResult>
      fetchKisSchedulerGuardedSellStatus() async {
    guardedSellStatusCalls += 1;
    return KisSchedulerGuardedSellResult.fromJson({
      'result': 'blocked',
      'reason': 'test',
    });
  }

  @override
  Future<KisSchedulerGuardedBuyResult>
      fetchKisSchedulerGuardedBuyStatus() async {
    guardedBuyStatusCalls += 1;
    return KisSchedulerGuardedBuyResult.fromJson({
      'result': 'blocked',
      'reason': 'test',
    });
  }
}

OpsSettings _opsSettings({
  bool dryRun = true,
  bool killSwitch = false,
  bool kisSchedulerEnabled = false,
  bool kisSchedulerDryRun = true,
  bool kisSchedulerLiveEnabled = false,
  bool kisSchedulerAllowRealOrders = false,
  bool kisSchedulerConfiguredAllowRealOrders = false,
  bool kisSchedulerSellEnabled = false,
  bool kisSchedulerBuyEnabled = false,
  bool kisLiveAutoSellEnabled = false,
  bool kisLiveAutoBuyEnabled = false,
  bool kisLimitedAutoStopLossEnabled = false,
  bool kisLimitedAutoTakeProfitEnabled = false,
  bool kisLimitedAutoBuyEnabled = false,
  bool kisSchedulerAllowLimitedAutoSell = false,
  bool kisSchedulerAllowLimitedAutoBuy = false,
}) {
  return OpsSettings(
    schedulerEnabled: false,
    botEnabled: false,
    dryRun: dryRun,
    killSwitch: killSwitch,
    brokerMode: 'Paper',
    defaultGateLevel: 2,
    maxDailyTrades: 5,
    maxDailyEntries: 2,
    minEntryScore: 65,
    minScoreGap: 3,
    kisSchedulerEnabled: kisSchedulerEnabled,
    kisSchedulerDryRun: kisSchedulerDryRun,
    kisSchedulerLiveEnabled: kisSchedulerLiveEnabled,
    kisSchedulerAllowRealOrders: kisSchedulerAllowRealOrders,
    kisSchedulerConfiguredAllowRealOrders:
        kisSchedulerConfiguredAllowRealOrders,
    kisSchedulerSellEnabled: kisSchedulerSellEnabled,
    kisSchedulerBuyEnabled: kisSchedulerBuyEnabled,
    kisLiveAutoSellEnabled: kisLiveAutoSellEnabled,
    kisLiveAutoBuyEnabled: kisLiveAutoBuyEnabled,
    kisLimitedAutoSellEnabled: false,
    kisLimitedAutoStopLossEnabled: kisLimitedAutoStopLossEnabled,
    kisLimitedAutoSellStopLossEnabled: kisLimitedAutoStopLossEnabled,
    kisLimitedAutoTakeProfitEnabled: kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoSellTakeProfitEnabled: kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoBuyEnabled: kisLimitedAutoBuyEnabled,
    kisSchedulerAllowLimitedAutoSell: kisSchedulerAllowLimitedAutoSell,
    kisSchedulerAllowLimitedAutoBuy: kisSchedulerAllowLimitedAutoBuy,
  );
}

OpsSettings _settingsWithPayload(
  OpsSettings settings,
  Map<String, dynamic> values,
) {
  final stopLoss = _valueBool(
    values,
    'kis_limited_auto_stop_loss_enabled',
    fallbackKey: 'kis_limited_auto_sell_stop_loss_enabled',
  );
  final takeProfit = _valueBool(
    values,
    'kis_limited_auto_take_profit_enabled',
    fallbackKey: 'kis_limited_auto_sell_take_profit_enabled',
  );
  return settings.copyWith(
    schedulerEnabled:
        _valueBool(values, 'scheduler_enabled') ?? settings.schedulerEnabled,
    dryRun: _valueBool(values, 'dry_run') ?? settings.dryRun,
    killSwitch: _valueBool(values, 'kill_switch') ?? settings.killSwitch,
    kisSchedulerEnabled: _valueBool(values, 'kis_scheduler_enabled') ??
        settings.kisSchedulerEnabled,
    kisSchedulerDryRun: _valueBool(values, 'kis_scheduler_dry_run') ??
        settings.kisSchedulerDryRun,
    kisSchedulerLiveEnabled: _valueBool(values, 'kis_scheduler_live_enabled') ??
        settings.kisSchedulerLiveEnabled,
    kisSchedulerAllowRealOrders:
        _valueBool(values, 'kis_scheduler_allow_real_orders') ??
            settings.kisSchedulerAllowRealOrders,
    kisSchedulerConfiguredAllowRealOrders:
        _valueBool(values, 'kis_scheduler_configured_allow_real_orders') ??
            settings.kisSchedulerConfiguredAllowRealOrders,
    kisSchedulerSellEnabled: _valueBool(values, 'kis_scheduler_sell_enabled') ??
        settings.kisSchedulerSellEnabled,
    kisSchedulerBuyEnabled: _valueBool(values, 'kis_scheduler_buy_enabled') ??
        settings.kisSchedulerBuyEnabled,
    kisLiveAutoSellEnabled: _valueBool(values, 'kis_live_auto_sell_enabled') ??
        settings.kisLiveAutoSellEnabled,
    kisLiveAutoBuyEnabled: _valueBool(values, 'kis_live_auto_buy_enabled') ??
        settings.kisLiveAutoBuyEnabled,
    kisLimitedAutoSellEnabled:
        _valueBool(values, 'kis_limited_auto_sell_enabled') ??
            settings.kisLimitedAutoSellEnabled,
    kisLimitedAutoStopLossEnabled:
        stopLoss ?? settings.kisLimitedAutoStopLossEnabled,
    kisLimitedAutoSellStopLossEnabled:
        stopLoss ?? settings.kisLimitedAutoSellStopLossEnabled,
    kisLimitedAutoTakeProfitEnabled:
        takeProfit ?? settings.kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoSellTakeProfitEnabled:
        takeProfit ?? settings.kisLimitedAutoSellTakeProfitEnabled,
    kisLimitedAutoBuyEnabled:
        _valueBool(values, 'kis_limited_auto_buy_enabled') ??
            settings.kisLimitedAutoBuyEnabled,
    kisSchedulerAllowLimitedAutoSell:
        _valueBool(values, 'kis_scheduler_allow_limited_auto_sell') ??
            settings.kisSchedulerAllowLimitedAutoSell,
    kisSchedulerAllowLimitedAutoBuy:
        _valueBool(values, 'kis_scheduler_allow_limited_auto_buy') ??
            settings.kisSchedulerAllowLimitedAutoBuy,
  );
}

bool? _valueBool(
  Map<String, dynamic> values,
  String key, {
  String? fallbackKey,
}) {
  if (values.containsKey(key)) return values[key] == true;
  if (fallbackKey != null && values.containsKey(fallbackKey)) {
    return values[fallbackKey] == true;
  }
  return null;
}
