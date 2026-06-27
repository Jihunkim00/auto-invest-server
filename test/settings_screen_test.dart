import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/core/i18n/app_language.dart';
import 'package:auto_invest_dashboard/core/network/api_client.dart';
import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/settings/settings_screen.dart';
import 'package:auto_invest_dashboard/models/kis_manual_order_safety_status.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_buy.dart';
import 'package:auto_invest_dashboard/models/kis_scheduler_guarded_sell.dart';
import 'package:auto_invest_dashboard/models/ops_settings.dart';
import 'package:auto_invest_dashboard/models/scheduler_status.dart';

void main() {
  testWidgets('Settings shows Operation Mode card', (tester) async {
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Global Safety'), findsOneWidget);
    expect(find.text('Operation Mode'), findsOneWidget);
    expect(find.byType(DropdownButtonFormField<String>), findsOneWidget);
    expect(find.text('Scope: Global'), findsOneWidget);
    expect(find.text('Affects: Alpaca + KIS'), findsOneWidget);

    final dropdown = find.byType(DropdownButtonFormField<String>);
    await tester.ensureVisible(dropdown);
    await tester.pumpAndSettle();
    await tester.tap(dropdown);
    await tester.pumpAndSettle();

    expect(find.text('Safe Mode'), findsWidgets);
    expect(find.text('Dry-run Simulation'), findsWidgets);
    expect(find.text('Manual Live Trading'), findsWidgets);
    expect(find.text('KIS Sell-only Automation'), findsWidgets);
    expect(find.text('Full Live Test Mode'), findsWidgets);

    controller.dispose();
  });

  testWidgets('Settings language selector switches UI immediately',
      (tester) async {
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(controller.appLanguage.code, 'ko');
    expect(find.text('언어'), findsOneWidget);
    expect(find.text('한국투자증권 안전 상태와 수동 실거래 상태입니다.'), findsOneWidget);

    await tester.tap(find.descendant(
      of: find.byKey(const ValueKey('app-language-selector')),
      matching: find.text('English'),
    ));
    await tester.pumpAndSettle();

    expect(controller.appLanguage.code, 'en');
    expect(find.text('Language'), findsOneWidget);
    expect(find.text('KIS safety and manual live status.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Settings shows broker scoped trading cards', (tester) async {
    _useTallSettingsViewport(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Global Safety'), findsOneWidget);
    expect(find.text('Alpaca / US Trading'), findsOneWidget);
    expect(find.text('KIS / KR Trading'), findsOneWidget);
    expect(find.text('GLOBAL'), findsWidgets);
    expect(find.text('ALPACA / US'), findsWidgets);
    expect(find.text('KIS / KR'), findsWidgets);

    controller.dispose();
  });

  testWidgets('selecting Safe Mode calls apply preset and updates UI',
      (tester) async {
    final api = _SettingsFakeApiClient(
      initialSettings: _opsSettingsForPreset('kis_sell_only_automation'),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    await _selectOperationMode(tester, 'Safe Mode');

    expect(api.applyPresetCalls, 1);
    expect(api.lastPreset, 'safe_mode');
    expect(controller.settings.currentOperationMode, 'safe_mode');
    expect(find.text('Safe Mode applied.'), findsOneWidget);

    controller.dispose();
  });

  testWidgets(
      'selecting KIS Sell-only Automation shows sell-only armed summary',
      (tester) async {
    final api = _SettingsFakeApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    await _selectOperationMode(tester, 'KIS Sell-only Automation');

    expect(api.lastPreset, 'kis_sell_only_automation');
    expect(
      find.text(
          'KIS sell-only live automation is armed. Auto-buy is disabled.'),
      findsOneWidget,
    );
    expect(find.text('LIVE SELL ARMED ON'), findsOneWidget);
    expect(find.text('LIVE BUY ARMED OFF'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('selecting Full Live Test Mode opens danger confirmation dialog',
      (tester) async {
    final api = _SettingsFakeApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    await _selectOperationMode(tester, 'Full Live Test Mode');

    expect(find.text('Full Live Test Mode'), findsWidgets);
    expect(find.text('This enables live buy and live sell automation.'),
        findsWidgets);
    expect(api.applyPresetCalls, 0);

    controller.dispose();
  });

  testWidgets('canceling Full Live Test Mode does not apply preset',
      (tester) async {
    final api = _SettingsFakeApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    await _selectOperationMode(tester, 'Full Live Test Mode');
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    expect(api.applyPresetCalls, 0);
    expect(controller.settings.currentOperationMode, 'safe_mode');

    controller.dispose();
  });

  testWidgets('confirming Full Live Test Mode applies preset', (tester) async {
    final api = _SettingsFakeApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));
    await _selectOperationMode(tester, 'Full Live Test Mode');
    await tester.tap(find.widgetWithText(FilledButton, 'Confirm'));
    await tester.pumpAndSettle();

    expect(api.applyPresetCalls, 1);
    expect(api.lastPreset, 'full_live_test_mode');
    expect(api.lastConfirmDangerous, isTrue);
    expect(controller.settings.currentOperationMode, 'full_live_test_mode');
    expect(find.text('LIVE BUY ARMED ON'), findsOneWidget);
    expect(find.text('LIVE SELL ARMED ON'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Risk Limits card edits numeric values', (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    await tester.enterText(
      find.widgetWithText(TextField, 'Max trades per day'),
      '7',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Max live orders per day'),
      '2',
    );
    await tester.enterText(
      find.widgetWithText(TextField, 'Max order notional %'),
      '4.5',
    );
    await tester.tap(find.text('Save Risk Limits'));
    await tester.pumpAndSettle();

    expect(api.updateOpsSettingsCalls, 1);
    expect(api.lastSettingsUpdate?['max_trades_per_day'], 7);
    expect(api.lastSettingsUpdate?['max_live_orders_per_day'], 2);
    expect(api.lastSettingsUpdate?['max_order_notional_pct'], 0.045);
    expect(controller.settings.maxDailyTrades, 7);
    expect(controller.settings.maxLiveOrdersPerDay, 2);

    controller.dispose();
  });

  testWidgets('KR no new entry after saves broker scoped key', (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient();
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    expect(find.widgetWithText(TextField, 'KR no new entry after'),
        findsOneWidget);
    expect(find.text('KST'), findsOneWidget);

    await tester.enterText(
      find.widgetWithText(TextField, 'KR no new entry after'),
      '14:40',
    );
    await tester.tap(find.text('Save KR Cutoff'));
    await tester.pumpAndSettle();

    expect(api.lastSettingsUpdate?['kr_no_new_entry_after'], '14:40');
    expect(controller.settings.krNoNewEntryAfter, '14:40');

    controller.dispose();
  });

  testWidgets('Schedule Control card displays next KR and US run',
      (tester) async {
    _useTallSettingsViewport(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Schedule Control'), findsOneWidget);
    expect(find.text('Next US run'), findsOneWidget);
    expect(find.textContaining('open_phase 2026-06-11T09:30'), findsWidgets);
    expect(find.text('Next KR run'), findsOneWidget);
    expect(find.textContaining('midday 2026-06-12T11:30'), findsWidgets);

    controller.dispose();
  });

  testWidgets('US no new entry after displays ET derived read-only label',
      (tester) async {
    _useTallSettingsViewport(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('US no new entry after'), findsOneWidget);
    expect(find.textContaining('15:45 ET'), findsOneWidget);
    expect(find.textContaining('derived / read-only'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('Advanced Flags collapsed by default', (tester) async {
    _useTallSettingsViewport(tester);
    final controller = _controller();

    await tester.pumpWidget(_wrap(controller));

    expect(find.text('Advanced Flags / Diagnostics'), findsOneWidget);
    expect(find.text('kis_scheduler_live_enabled'), findsNothing);

    controller.dispose();
  });

  testWidgets('dangerous_mixed renders red warning', (tester) async {
    final api = _SettingsFakeApiClient(
      initialSettings: _opsSettingsForPreset('full_live_test_mode'),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    expect(find.byKey(const Key('settings-warning-dangerous_mixed')),
        findsOneWidget);
    expect(find.text('FULL LIVE TEST MODE ON'), findsOneWidget);
    expect(find.text('LIVE BUY ARMED ON'), findsOneWidget);
    expect(find.text('Scope: KIS / KR'), findsOneWidget);
    expect(find.text('Warning: dangerous_mixed'), findsOneWidget);

    controller.dispose();
  });

  testWidgets('old no_new_entry_after is displayed as KR cutoff',
      (tester) async {
    _useTallSettingsViewport(tester);
    final api = _SettingsFakeApiClient(
      initialSettings: _opsSettings(noNewEntryAfter: '14:35'),
    );
    final controller = _controller(api);

    await tester.pumpWidget(_wrap(controller));

    expect(find.widgetWithText(TextField, 'KR no new entry after'),
        findsOneWidget);
    expect(find.text('14:35'), findsOneWidget);

    controller.dispose();
  });
}

DashboardController _controller([_SettingsFakeApiClient? api]) {
  final fake = api ?? _SettingsFakeApiClient();
  return DashboardController(fake, autoload: false)
    ..selectedProvider = SelectedProvider.kis
    ..settings = fake.currentSettings
    ..schedulerStatus = fake.currentStatus
    ..kisSafetyStatus = fake.safetyStatus;
}

Widget _wrap(DashboardController controller) {
  return MaterialApp(
    theme: ThemeData.dark(),
    home: Scaffold(body: SettingsScreen(controller: controller)),
  );
}

void _useTallSettingsViewport(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 6000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.resetPhysicalSize);
  addTearDown(tester.view.resetDevicePixelRatio);
}

Future<void> _selectOperationMode(WidgetTester tester, String label) async {
  final dropdown = find.byType(DropdownButtonFormField<String>);
  await tester.ensureVisible(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(dropdown);
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

class _SettingsFakeApiClient extends ApiClient {
  _SettingsFakeApiClient({OpsSettings? initialSettings})
      : currentSettings = initialSettings ?? _opsSettings() {
    currentStatus = _schedulerStatusForSettings(currentSettings);
  }

  OpsSettings currentSettings;
  late SchedulerStatus currentStatus;
  int getOpsSettingsCalls = 0;
  int updateOpsSettingsCalls = 0;
  int applyPresetCalls = 0;
  int schedulerStatusCalls = 0;
  int guardedSellStatusCalls = 0;
  int guardedBuyStatusCalls = 0;
  String? lastPreset;
  bool? lastConfirmDangerous;
  Map<String, dynamic>? lastSettingsUpdate;

  KisManualOrderSafetyStatus get safetyStatus => KisManualOrderSafetyStatus(
        runtimeDryRun: currentSettings.dryRun,
        killSwitch: currentSettings.killSwitch,
        kisEnabled: true,
        kisRealOrderEnabled: true,
        marketOpen: true,
        entryAllowedNow: true,
        noNewEntryAfter: '15:00',
      );

  @override
  Future<OpsSettings> getOpsSettings() async {
    getOpsSettingsCalls += 1;
    return currentSettings;
  }

  @override
  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    updateOpsSettingsCalls += 1;
    lastSettingsUpdate = Map<String, dynamic>.from(values);
    currentSettings = _settingsWithPayload(currentSettings, values);
    currentStatus = _schedulerStatusForSettings(currentSettings);
  }

  @override
  Future<Map<String, dynamic>> applyOpsSettingsPreset({
    required String preset,
    bool confirmDangerous = false,
  }) async {
    applyPresetCalls += 1;
    lastPreset = preset;
    lastConfirmDangerous = confirmDangerous;
    if (preset == 'full_live_test_mode' && !confirmDangerous) {
      return {
        'preset': preset,
        'applied': false,
        'requires_confirmation': true,
        'warning_level': 'dangerous_mixed',
      };
    }
    currentSettings = _opsSettingsForPreset(preset);
    currentStatus = _schedulerStatusForSettings(currentSettings);
    return {
      'preset': preset,
      'applied': true,
      'requires_confirmation': false,
      'warning_level': currentStatus.riskSummary.warningLevel,
    };
  }

  @override
  Future<SchedulerStatus> fetchSchedulerStatus() async {
    schedulerStatusCalls += 1;
    return currentStatus;
  }

  @override
  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    return safetyStatus;
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
  String currentOperationMode = 'safe_mode',
  bool schedulerEnabled = false,
  bool dryRun = true,
  bool killSwitch = false,
  bool kisSchedulerEnabled = false,
  bool kisSchedulerDryRun = true,
  bool kisSchedulerLiveEnabled = false,
  bool kisSchedulerAllowRealOrders = false,
  bool kisSchedulerConfiguredAllowRealOrders = false,
  bool kisSchedulerSellEnabled = false,
  bool kisSchedulerBuyEnabled = false,
  bool kisSchedulerAllowLimitedAutoSell = false,
  bool kisSchedulerAllowLimitedAutoBuy = false,
  bool kisLiveAutoSellEnabled = false,
  bool kisLiveAutoBuyEnabled = false,
  bool kisLimitedAutoStopLossEnabled = false,
  bool kisLimitedAutoTakeProfitEnabled = false,
  bool kisLimitedAutoBuyEnabled = false,
  int maxDailyTrades = 5,
  int maxLiveOrdersPerDay = 1,
  int maxPositions = 3,
  double maxOrderNotionalPct = 0.03,
  double maxPositionPct = 0.03,
  double dailyMaxLossPct = 0,
  String noNewEntryAfter = '14:50',
}) {
  return OpsSettings(
    schedulerEnabled: schedulerEnabled,
    botEnabled: false,
    dryRun: dryRun,
    killSwitch: killSwitch,
    brokerMode: 'Paper',
    defaultGateLevel: 2,
    maxDailyTrades: maxDailyTrades,
    maxDailyEntries: 2,
    minEntryScore: 65,
    minScoreGap: 3,
    currentOperationMode: currentOperationMode,
    maxLiveOrdersPerDay: maxLiveOrdersPerDay,
    maxPositions: maxPositions,
    maxOrderNotionalPct: maxOrderNotionalPct,
    maxPositionPct: maxPositionPct,
    dailyMaxLossPct: dailyMaxLossPct,
    noNewEntryAfter: noNewEntryAfter,
    krNoNewEntryAfter: noNewEntryAfter,
    kisSchedulerEnabled: kisSchedulerEnabled,
    kisSchedulerDryRun: kisSchedulerDryRun,
    kisSchedulerLiveEnabled: kisSchedulerLiveEnabled,
    kisSchedulerAllowRealOrders: kisSchedulerAllowRealOrders,
    kisSchedulerConfiguredAllowRealOrders:
        kisSchedulerConfiguredAllowRealOrders,
    kisSchedulerSellEnabled: kisSchedulerSellEnabled,
    kisSchedulerBuyEnabled: kisSchedulerBuyEnabled,
    kisSchedulerAllowLimitedAutoSell: kisSchedulerAllowLimitedAutoSell,
    kisSchedulerAllowLimitedAutoBuy: kisSchedulerAllowLimitedAutoBuy,
    kisLiveAutoSellEnabled: kisLiveAutoSellEnabled,
    kisLiveAutoBuyEnabled: kisLiveAutoBuyEnabled,
    kisLimitedAutoStopLossEnabled: kisLimitedAutoStopLossEnabled,
    kisLimitedAutoSellStopLossEnabled: kisLimitedAutoStopLossEnabled,
    kisLimitedAutoTakeProfitEnabled: kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoSellTakeProfitEnabled: kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoBuyEnabled: kisLimitedAutoBuyEnabled,
    kisLimitedAutoBuyNoNewEntryAfter: noNewEntryAfter,
  );
}

OpsSettings _opsSettingsForPreset(String preset) {
  switch (preset) {
    case 'kis_sell_only_automation':
      return _opsSettings(
        currentOperationMode: preset,
        schedulerEnabled: true,
        dryRun: false,
        kisSchedulerEnabled: true,
        kisSchedulerDryRun: false,
        kisSchedulerLiveEnabled: true,
        kisSchedulerAllowRealOrders: true,
        kisSchedulerConfiguredAllowRealOrders: true,
        kisSchedulerSellEnabled: true,
        kisSchedulerAllowLimitedAutoSell: true,
        kisLiveAutoSellEnabled: true,
        kisLimitedAutoStopLossEnabled: true,
      );
    case 'full_live_test_mode':
      return _opsSettings(
        currentOperationMode: preset,
        schedulerEnabled: true,
        dryRun: false,
        kisSchedulerEnabled: true,
        kisSchedulerDryRun: false,
        kisSchedulerLiveEnabled: true,
        kisSchedulerAllowRealOrders: true,
        kisSchedulerConfiguredAllowRealOrders: true,
        kisSchedulerSellEnabled: true,
        kisSchedulerBuyEnabled: true,
        kisSchedulerAllowLimitedAutoSell: true,
        kisSchedulerAllowLimitedAutoBuy: true,
        kisLiveAutoSellEnabled: true,
        kisLiveAutoBuyEnabled: true,
        kisLimitedAutoStopLossEnabled: true,
        kisLimitedAutoBuyEnabled: true,
      );
    case 'manual_live_trading':
      return _opsSettings(currentOperationMode: preset, dryRun: false);
    case 'dry_run_simulation':
      return _opsSettings(
        currentOperationMode: preset,
        schedulerEnabled: true,
        kisSchedulerEnabled: true,
        kisSchedulerDryRun: true,
      );
    case 'safe_mode':
    default:
      return _opsSettings(currentOperationMode: 'safe_mode');
  }
}

OpsSettings _settingsWithPayload(
  OpsSettings settings,
  Map<String, dynamic> values,
) {
  final stopLoss = _valueBool(
    values,
    'stop_loss_enabled',
    fallbackKey: 'kis_limited_auto_stop_loss_enabled',
  );
  final takeProfit = _valueBool(
    values,
    'take_profit_enabled',
    fallbackKey: 'kis_limited_auto_take_profit_enabled',
  );
  final krNoNewEntryAfter = _valueString(values, 'kr_no_new_entry_after') ??
      _valueString(values, 'no_new_entry_after') ??
      _valueString(values, 'kis_limited_auto_buy_no_new_entry_after');
  return settings.copyWith(
    schedulerEnabled:
        _valueBool(values, 'scheduler_enabled') ?? settings.schedulerEnabled,
    dryRun: _valueBool(values, 'dry_run') ?? settings.dryRun,
    maxDailyTrades:
        _valueInt(values, 'max_trades_per_day') ?? settings.maxDailyTrades,
    maxLiveOrdersPerDay: _valueInt(values, 'max_live_orders_per_day') ??
        settings.maxLiveOrdersPerDay,
    maxPositions: _valueInt(values, 'max_positions') ?? settings.maxPositions,
    maxOrderNotionalPct: _valueDouble(values, 'max_order_notional_pct') ??
        settings.maxOrderNotionalPct,
    maxPositionPct:
        _valueDouble(values, 'max_position_pct') ?? settings.maxPositionPct,
    dailyMaxLossPct:
        _valueDouble(values, 'daily_max_loss_pct') ?? settings.dailyMaxLossPct,
    noNewEntryAfter: krNoNewEntryAfter ?? settings.noNewEntryAfter,
    krNoNewEntryAfter: krNoNewEntryAfter ?? settings.krNoNewEntryAfter,
    kisLimitedAutoBuyNoNewEntryAfter:
        krNoNewEntryAfter ?? settings.kisLimitedAutoBuyNoNewEntryAfter,
    kisSchedulerEnabled: _valueBool(values, 'kr_scheduler_enabled') ??
        _valueBool(values, 'kis_scheduler_enabled') ??
        settings.kisSchedulerEnabled,
    kisLimitedAutoStopLossEnabled:
        stopLoss ?? settings.kisLimitedAutoStopLossEnabled,
    kisLimitedAutoSellStopLossEnabled:
        stopLoss ?? settings.kisLimitedAutoSellStopLossEnabled,
    kisLimitedAutoTakeProfitEnabled:
        takeProfit ?? settings.kisLimitedAutoTakeProfitEnabled,
    kisLimitedAutoSellTakeProfitEnabled:
        takeProfit ?? settings.kisLimitedAutoSellTakeProfitEnabled,
  );
}

SchedulerStatus _schedulerStatusForSettings(OpsSettings settings) {
  final risk = _riskSummaryForSettings(settings);
  final mode = settings.currentOperationMode;
  final summary = switch (mode) {
    'kis_sell_only_automation' =>
      'KIS sell-only live automation is armed. Auto-buy is disabled.',
    'full_live_test_mode' =>
      'Full live test mode is armed. Live buy and live sell automation are enabled.',
    _ =>
      'Safe mode is active. Scheduler live buy and sell automation are disabled.',
  };
  final warningMessage = risk.warningLevel == 'armed_sell_only'
      ? 'LIVE SELL ARMED. Auto-buy is disabled. Daily live orders remaining: 1.'
      : risk.warningLevel == 'dangerous_mixed'
          ? 'LIVE BUY ARMED and LIVE SELL ARMED may be possible. Full live test mode is dangerous.'
          : 'No scheduler live buy or sell automation is armed.';
  return SchedulerStatus(
    runtimeSchedulerEnabled: settings.schedulerEnabled,
    currentOperationMode: mode,
    userFriendlySummary: summary,
    riskSummary: risk,
    liveOrderPossible: risk.liveBuyArmed || risk.liveSellArmed,
    liveBuyPossible: risk.liveBuyArmed,
    liveSellPossible: risk.liveSellArmed,
    dailyLiveOrderRemaining: risk.dailyLiveOrderRemaining,
    warningMessage: warningMessage,
    us: const MarketSchedulerStatus(
      enabledForScheduler: true,
      timezone: 'America/New_York',
      slots: ['open_phase 09:30'],
      nextSlotName: 'open_phase',
      nextSlotTimeLocal: '2026-06-11T09:30',
    ),
    kr: MarketSchedulerStatus(
      enabledForScheduler: settings.kisSchedulerEnabled,
      timezone: 'Asia/Seoul',
      slots: const ['midday 11:30'],
      nextSlotName: 'midday',
      nextSlotTimeLocal: '2026-06-12T11:30',
      realOrderSchedulerEnabled: risk.liveSellArmed || risk.liveBuyArmed,
      riskSummary: risk,
    ),
  );
}

SchedulerRiskSummary _riskSummaryForSettings(OpsSettings settings) {
  final buyArmed = !settings.dryRun &&
      !settings.killSwitch &&
      (settings.kisSchedulerBuyEnabled ||
          settings.kisSchedulerAllowLimitedAutoBuy ||
          settings.kisLiveAutoBuyEnabled ||
          settings.kisLimitedAutoBuyEnabled);
  final sellArmed = !settings.dryRun &&
      !settings.killSwitch &&
      settings.schedulerEnabled &&
      settings.kisSchedulerEnabled &&
      settings.kisSchedulerLiveEnabled &&
      settings.kisSchedulerAllowRealOrders &&
      settings.kisSchedulerConfiguredAllowRealOrders &&
      settings.kisSchedulerSellEnabled &&
      settings.kisSchedulerAllowLimitedAutoSell &&
      settings.kisLiveAutoSellEnabled &&
      settings.kisLimitedAutoStopLossEnabled;
  final warningLevel = buyArmed
      ? 'dangerous_mixed'
      : sellArmed
          ? 'armed_sell_only'
          : 'safe';
  return SchedulerRiskSummary(
    liveSellArmed: sellArmed,
    liveBuyArmed: buyArmed,
    sellOnlyMode: sellArmed && !buyArmed,
    dailyLiveOrderLimit: settings.maxLiveOrdersPerDay,
    dailyLiveOrderRemaining: sellArmed || buyArmed ? 1 : null,
    maxNotionalPct: settings.maxOrderNotionalPct,
    dryRun: settings.dryRun,
    killSwitch: settings.killSwitch,
    safeModeActive: warningLevel == 'safe',
    riskyFlags: buyArmed ? const ['kis_scheduler_buy_enabled'] : const [],
    blockingFlags: const [],
    warningLevel: warningLevel,
    sellGateEnabled: settings.kisLimitedAutoStopLossEnabled,
    buyGateEnabled: buyArmed,
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

int? _valueInt(Map<String, dynamic> values, String key) {
  if (!values.containsKey(key)) return null;
  final value = values[key];
  if (value is num) return value.toInt();
  return int.tryParse(value?.toString() ?? '');
}

double? _valueDouble(Map<String, dynamic> values, String key) {
  if (!values.containsKey(key)) return null;
  final value = values[key];
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}

String? _valueString(Map<String, dynamic> values, String key) {
  final value = values[key]?.toString().trim();
  if (value == null || value.isEmpty) return null;
  return value;
}
