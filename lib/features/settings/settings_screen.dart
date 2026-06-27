import 'package:flutter/material.dart';

import '../../core/i18n/app_language.dart';
import '../../core/widgets/confirm_action_dialog.dart';
import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final strings = controller.strings;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Expanded(
                  child: Text(
                    strings.settings,
                    style: const TextStyle(
                      fontSize: 28,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              Text(
                controller.selectedProvider == SelectedProvider.kis
                    ? strings.settingsKisSubtitle
                    : strings.settingsAlpacaSubtitle,
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              _LanguageCard(controller: controller),
              const SizedBox(height: 12),
              _OperationModeCard(controller: controller),
              const SizedBox(height: 12),
              _AlpacaUsTradingCard(controller: controller),
              const SizedBox(height: 12),
              _KisKrTradingCard(controller: controller),
              const SizedBox(height: 12),
              _ScheduleControlCard(controller: controller),
              const SizedBox(height: 12),
              _RiskLimitsCard(controller: controller),
              const SizedBox(height: 12),
              _ExitRulesCard(controller: controller),
              const SizedBox(height: 12),
              _AdvancedFlagsCard(controller: controller),
            ],
          ),
        );
      },
    );
  }
}

class _LanguageCard extends StatelessWidget {
  const _LanguageCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _CardHeader(
          icon: Icons.language,
          title: strings.language,
        ),
        const SizedBox(height: 8),
        Text(
          strings.languageDescription,
          style: const TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 10),
        SegmentedButton<AppLanguage>(
          key: const ValueKey('app-language-selector'),
          showSelectedIcon: false,
          segments: [
            ButtonSegment<AppLanguage>(
              value: AppLanguage.korean,
              label: Text(strings.korean),
              icon: const Icon(Icons.translate, size: 16),
            ),
            ButtonSegment<AppLanguage>(
              value: AppLanguage.english,
              label: Text(strings.english),
              icon: const Icon(Icons.language, size: 16),
            ),
          ],
          selected: {controller.appLanguage},
          onSelectionChanged: (selection) {
            controller.setAppLanguage(selection.first);
          },
        ),
        const SizedBox(height: 8),
        Text(
          strings.languagePersistenceNote,
          style: const TextStyle(color: Colors.white54, fontSize: 12),
        ),
      ]),
    );
  }
}

class _OperationModeCard extends StatelessWidget {
  const _OperationModeCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final mode = _currentMode(controller);
    final loading = controller.kisAutomationSettingsLoading;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _CardHeader(
          icon: Icons.power_settings_new,
          title: 'Global Safety',
          trailing: loading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : null,
        ),
        const SizedBox(height: 10),
        _StatusBanner(controller: controller),
        const SizedBox(height: 10),
        const Text(
          'Operation Mode',
          style: TextStyle(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 6),
        _PresetScopeDetails(mode: mode),
        const SizedBox(height: 10),
        DropdownButtonFormField<String>(
          key: ValueKey('operation-mode-$mode'),
          initialValue:
              _operationModeOptions.any((option) => option.value == mode)
                  ? mode
                  : null,
          decoration: const InputDecoration(labelText: 'Operation mode'),
          items: [
            for (final option in _operationModeOptions)
              DropdownMenuItem<String>(
                value: option.value,
                child: Text(option.label),
              ),
          ],
          onChanged: loading
              ? null
              : (value) {
                  if (value == null || value == mode) return;
                  _applyMode(context, controller, value);
                },
        ),
        const SizedBox(height: 8),
        _ScopedSwitchTile(
          scope: 'GLOBAL',
          title: 'Dry-run',
          subtitle: 'Applies to manual and scheduler live order guards.',
          value: controller.settings.dryRun,
          onChanged: loading ? null : (value) => controller.setDryRun(value),
        ),
        _ScopedSwitchTile(
          scope: 'GLOBAL',
          title: 'Kill switch',
          subtitle: 'Blocks manual and scheduler order paths.',
          value: controller.settings.killSwitch,
          onChanged:
              loading ? null : (value) => controller.toggleKillSwitch(value),
        ),
        _ScopedSwitchTile(
          scope: 'GLOBAL',
          title: 'Global scheduler',
          subtitle: 'Required before Alpaca or KIS scheduler checks can run.',
          value: controller.settings.schedulerEnabled,
          onChanged: loading
              ? null
              : (value) => _saveSettings(
                    context,
                    controller,
                    {'scheduler_enabled': value},
                    'Global scheduler',
                  ),
        ),
        if (mode == 'full_live_test_mode') ...[
          const SizedBox(height: 6),
          const Text(
            'KIS/KR live buy and live sell automation. Red confirmation required.',
            style: TextStyle(color: Colors.redAccent),
          ),
        ],
        if (controller.latestSettingsChangeSummary != null) ...[
          const SizedBox(height: 10),
          _SettingsChangeSummary(text: controller.latestSettingsChangeSummary!),
        ],
      ]),
    );
  }
}

class _AlpacaUsTradingCard extends StatelessWidget {
  const _AlpacaUsTradingCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final status = controller.schedulerStatus;
    final usCutoff = settings.usNoNewEntryAfter.isNotEmpty
        ? settings.usNoNewEntryAfter
        : status.us.noNewEntryAfter ?? '15:45';
    final derivedLabel =
        settings.usNoNewEntryAfterDerived ? 'derived / read-only' : 'runtime';
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const _CardHeader(
          icon: Icons.public_outlined,
          title: 'Alpaca / US Trading',
        ),
        const SizedBox(height: 8),
        _InfoRow(
          label: 'US scheduler enabled',
          value: status.us.enabledForScheduler ? 'ON' : 'OFF',
          scope: 'ALPACA / US',
        ),
        _InfoRow(
          label: 'US next run',
          value: _nextRun(status.us),
          scope: 'ALPACA / US',
        ),
        _InfoRow(
          label: 'US timezone',
          value: 'America/New_York',
          scope: 'ALPACA / US',
        ),
        _InfoRow(
          label: 'US no new entry after',
          value: '$usCutoff ET ($derivedLabel)',
          scope: 'ALPACA / US',
        ),
        const Padding(
          padding: EdgeInsets.only(top: 6),
          child: Text(
            'Applied in America/New_York time for Alpaca/US entry checks.',
            style: TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ),
        _InfoRow(
          label: 'Alpaca status',
          value: settings.brokerMode,
          scope: 'ALPACA / US',
        ),
      ]),
    );
  }
}

class _KisKrTradingCard extends StatefulWidget {
  const _KisKrTradingCard({required this.controller});

  final DashboardController controller;

  @override
  State<_KisKrTradingCard> createState() => _KisKrTradingCardState();
}

class _KisKrTradingCardState extends State<_KisKrTradingCard> {
  final _krNoNewEntryAfter = TextEditingController();
  String _lastCutoff = '';
  bool _editing = false;

  @override
  void initState() {
    super.initState();
    _syncFromSettings(force: true);
  }

  @override
  void didUpdateWidget(covariant _KisKrTradingCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncFromSettings();
  }

  @override
  void dispose() {
    _krNoNewEntryAfter.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final settings = widget.controller.settings;
    final status = widget.controller.schedulerStatus;
    final risk = status.riskSummary;
    final loading = widget.controller.kisAutomationSettingsLoading;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const _CardHeader(
          icon: Icons.account_balance_outlined,
          title: 'KIS / KR Trading',
        ),
        const SizedBox(height: 8),
        _ScopedSwitchTile(
          scope: 'KIS / KR',
          title: 'KIS scheduler enabled',
          subtitle: 'Controls KIS/KR scheduler automation only.',
          value: settings.kisSchedulerEnabled,
          onChanged: loading
              ? null
              : (value) => _saveSettings(
                    context,
                    widget.controller,
                    {'kr_scheduler_enabled': value},
                    'KIS scheduler',
                  ),
        ),
        _InfoRow(
          label: 'KR scheduler mode',
          value: _krModeSummary(settings),
          scope: 'KIS / KR',
        ),
        _InfoRow(
          label: 'KR next run',
          value: _nextRun(status.kr),
          scope: 'KIS / KR',
        ),
        _InfoRow(
          label: 'KR timezone',
          value: 'Asia/Seoul',
          scope: 'KIS / KR',
        ),
        _ScopedTextField(
          scope: 'KIS / KR',
          label: 'KR no new entry after',
          controller: _krNoNewEntryAfter,
          suffixText: 'KST',
          helperText:
              'Applied in Asia/Seoul time for KIS/KR scheduler entry checks.',
          onChanged: () {
            if (!_editing) setState(() => _editing = true);
          },
        ),
        const SizedBox(height: 8),
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton.icon(
            onPressed: loading ? null : _saveCutoff,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Save KR Cutoff'),
          ),
        ),
        _InfoRow(
          label: 'KIS live buy armed',
          value: risk.liveBuyArmed ? 'ON' : 'OFF',
          scope: 'KIS / KR',
        ),
        _InfoRow(
          label: 'KIS live sell armed',
          value: risk.liveSellArmed ? 'ON' : 'OFF',
          scope: 'KIS / KR',
        ),
        _InfoRow(
          label: 'KIS warning level',
          value: risk.warningLevel,
          scope: 'KIS / KR',
        ),
      ]),
    );
  }

  void _syncFromSettings({bool force = false}) {
    final cutoff = widget.controller.settings.krNoNewEntryAfter.isNotEmpty
        ? widget.controller.settings.krNoNewEntryAfter
        : widget.controller.settings.noNewEntryAfter;
    if (!force && (_editing || cutoff == _lastCutoff)) return;
    _lastCutoff = cutoff;
    _krNoNewEntryAfter.text = cutoff;
  }

  Future<void> _saveCutoff() async {
    final result = await widget.controller.updateKisAutomationSettings(
      {'kr_no_new_entry_after': _krNoNewEntryAfter.text.trim()},
      label: 'KR no new entry after',
    );
    if (!mounted) return;
    _editing = false;
    _syncFromSettings(force: true);
    _showResult(context, result);
  }
}

class _ScheduleControlCard extends StatelessWidget {
  const _ScheduleControlCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final status = controller.schedulerStatus;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const _CardHeader(
          icon: Icons.calendar_month_outlined,
          title: 'Schedule Control',
        ),
        const SizedBox(height: 8),
        _InfoRow(
          label: 'Global scheduler',
          value: settings.schedulerEnabled ? 'ON' : 'OFF',
          scope: 'GLOBAL',
        ),
        _InfoRow(
          label: 'US schedule enabled',
          value: status.us.enabledForScheduler ? 'ON' : 'OFF',
          scope: 'ALPACA / US',
        ),
        _InfoRow(
          label: 'KR schedule enabled',
          value: settings.kisSchedulerEnabled ? 'ON' : 'OFF',
          scope: 'KIS / KR',
        ),
        _InfoRow(
          label: 'Next US run',
          value: _nextRun(status.us),
          scope: 'ALPACA / US',
        ),
        _InfoRow(
          label: 'Next KR run',
          value: _nextRun(status.kr),
          scope: 'KIS / KR',
        ),
        _InfoRow(
          label: 'KR mode summary',
          value: _krModeSummary(settings),
          scope: 'KIS / KR',
        ),
      ]),
    );
  }
}

class _RiskLimitsCard extends StatefulWidget {
  const _RiskLimitsCard({required this.controller});

  final DashboardController controller;

  @override
  State<_RiskLimitsCard> createState() => _RiskLimitsCardState();
}

class _RiskLimitsCardState extends State<_RiskLimitsCard> {
  final _maxTrades = TextEditingController();
  final _maxLiveOrders = TextEditingController();
  final _maxPositions = TextEditingController();
  final _maxOrderNotionalPct = TextEditingController();
  final _maxPositionPct = TextEditingController();
  final _dailyMaxLossPct = TextEditingController();
  String _lastSignature = '';
  bool _editing = false;

  @override
  void initState() {
    super.initState();
    _syncFromSettings(force: true);
  }

  @override
  void didUpdateWidget(covariant _RiskLimitsCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncFromSettings();
  }

  @override
  void dispose() {
    _maxTrades.dispose();
    _maxLiveOrders.dispose();
    _maxPositions.dispose();
    _maxOrderNotionalPct.dispose();
    _maxPositionPct.dispose();
    _dailyMaxLossPct.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final loading = widget.controller.kisAutomationSettingsLoading;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const _CardHeader(
          icon: Icons.speed_outlined,
          title: 'Risk Limits',
        ),
        const SizedBox(height: 12),
        _NumberField(
          label: 'Max trades per day',
          scope: 'GLOBAL',
          controller: _maxTrades,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max live orders per day',
          scope: 'KIS / KR',
          controller: _maxLiveOrders,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max positions',
          scope: 'GLOBAL',
          controller: _maxPositions,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max order notional %',
          scope: 'KIS / KR',
          controller: _maxOrderNotionalPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max position %',
          scope: 'KIS / KR',
          controller: _maxPositionPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Daily max loss %',
          scope: 'GLOBAL',
          controller: _dailyMaxLossPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton.icon(
            onPressed: loading ? null : _save,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Save Risk Limits'),
          ),
        ),
      ]),
    );
  }

  void _markEditing() {
    if (!_editing) setState(() => _editing = true);
  }

  void _syncFromSettings({bool force = false}) {
    final settings = widget.controller.settings;
    final signature = [
      settings.maxDailyTrades,
      settings.maxLiveOrdersPerDay,
      settings.maxPositions,
      settings.maxOrderNotionalPct,
      settings.maxPositionPct,
      settings.dailyMaxLossPct,
    ].join('|');
    if (!force && (_editing || signature == _lastSignature)) return;
    _lastSignature = signature;
    _maxTrades.text = settings.maxDailyTrades.toString();
    _maxLiveOrders.text = settings.maxLiveOrdersPerDay.toString();
    _maxPositions.text = settings.maxPositions.toString();
    _maxOrderNotionalPct.text =
        _formatPercentInput(settings.maxOrderNotionalPct);
    _maxPositionPct.text = _formatPercentInput(settings.maxPositionPct);
    _dailyMaxLossPct.text = _formatPercentInput(settings.dailyMaxLossPct);
  }

  Future<void> _save() async {
    final payload = <String, dynamic>{
      'max_trades_per_day': _intValue(_maxTrades.text),
      'max_live_orders_per_day': _intValue(_maxLiveOrders.text),
      'max_positions': _intValue(_maxPositions.text),
      'max_order_notional_pct': _percentValue(_maxOrderNotionalPct.text),
      'max_position_pct': _percentValue(_maxPositionPct.text),
      'daily_max_loss_pct': _percentValue(_dailyMaxLossPct.text),
    }..removeWhere((_, value) => value == null || value == '');
    final result = await widget.controller.updateKisAutomationSettings(
      payload,
      label: 'Risk Limits',
    );
    if (!mounted) return;
    _editing = false;
    _syncFromSettings(force: true);
    _showResult(context, result);
  }
}

class _ExitRulesCard extends StatefulWidget {
  const _ExitRulesCard({required this.controller});

  final DashboardController controller;

  @override
  State<_ExitRulesCard> createState() => _ExitRulesCardState();
}

class _ExitRulesCardState extends State<_ExitRulesCard> {
  final _stopLossPct = TextEditingController();
  final _takeProfitPct = TextEditingController();
  bool _stopLossEnabled = false;
  bool _takeProfitEnabled = false;
  String _lastSignature = '';
  bool _editing = false;

  @override
  void initState() {
    super.initState();
    _syncFromSettings(force: true);
  }

  @override
  void didUpdateWidget(covariant _ExitRulesCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncFromSettings();
  }

  @override
  void dispose() {
    _stopLossPct.dispose();
    _takeProfitPct.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final loading = widget.controller.kisAutomationSettingsLoading;
    final risk = widget.controller.schedulerStatus.riskSummary;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const _CardHeader(
          icon: Icons.exit_to_app_outlined,
          title: 'Exit Rules',
        ),
        _ScopedSwitchTile(
          scope: 'KIS / KR',
          title: 'Stop-loss enabled',
          subtitle: 'KIS/KR sell automation gate.',
          value: _stopLossEnabled,
          onChanged: loading
              ? null
              : (value) => setState(() {
                    _editing = true;
                    _stopLossEnabled = value;
                  }),
        ),
        _NumberField(
          label: 'Stop-loss %',
          scope: 'KIS / KR',
          controller: _stopLossPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        _ScopedSwitchTile(
          scope: 'KIS / KR',
          title: 'Take-profit enabled',
          subtitle: 'KIS/KR sell automation gate.',
          value: _takeProfitEnabled,
          onChanged: loading
              ? null
              : (value) => setState(() {
                    _editing = true;
                    _takeProfitEnabled = value;
                  }),
        ),
        _NumberField(
          label: 'Take-profit %',
          scope: 'KIS / KR',
          controller: _takeProfitPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        if (_takeProfitEnabled &&
            (risk.liveSellArmed ||
                widget.controller.settings.kisSchedulerLiveEnabled))
          const Padding(
            padding: EdgeInsets.only(top: 8),
            child: Text(
              'Take-profit execution warning if live enabled',
              style: TextStyle(
                color: Colors.orangeAccent,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
        const SizedBox(height: 12),
        Align(
          alignment: Alignment.centerRight,
          child: FilledButton.icon(
            onPressed: loading ? null : _save,
            icon: const Icon(Icons.save_outlined),
            label: const Text('Save Exit Rules'),
          ),
        ),
      ]),
    );
  }

  void _markEditing() {
    if (!_editing) setState(() => _editing = true);
  }

  void _syncFromSettings({bool force = false}) {
    final settings = widget.controller.settings;
    final stopLoss = settings.kisLimitedAutoStopLossEnabled ||
        settings.kisLimitedAutoSellStopLossEnabled;
    final takeProfit = settings.kisLimitedAutoTakeProfitEnabled ||
        settings.kisLimitedAutoSellTakeProfitEnabled;
    final signature = [
      stopLoss,
      takeProfit,
      settings.stopLossPct,
      settings.takeProfitPct,
    ].join('|');
    if (!force && (_editing || signature == _lastSignature)) return;
    _lastSignature = signature;
    _stopLossEnabled = stopLoss;
    _takeProfitEnabled = takeProfit;
    _stopLossPct.text = _formatPercentInput(settings.stopLossPct);
    _takeProfitPct.text = _formatPercentInput(settings.takeProfitPct);
  }

  Future<void> _save() async {
    final result = await widget.controller.updateKisAutomationSettings(
      {
        'stop_loss_enabled': _stopLossEnabled,
        'stop_loss_pct': _percentValue(_stopLossPct.text),
        'take_profit_enabled': _takeProfitEnabled,
        'take_profit_pct': _percentValue(_takeProfitPct.text),
      },
      label: 'Exit Rules',
    );
    if (!mounted) return;
    _editing = false;
    _syncFromSettings(force: true);
    _showResult(context, result);
  }
}

class _AdvancedFlagsCard extends StatelessWidget {
  const _AdvancedFlagsCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final risk = controller.schedulerStatus.riskSummary;
    final flags = <_AdvancedFlag>[
      _AdvancedFlag('dry_run', settings.dryRun),
      _AdvancedFlag('kill_switch', settings.killSwitch, dangerous: true),
      _AdvancedFlag(
          'kis_scheduler_live_enabled', settings.kisSchedulerLiveEnabled,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_allow_real_orders',
          settings.kisSchedulerAllowRealOrders,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_configured_allow_real_orders',
          settings.kisSchedulerConfiguredAllowRealOrders,
          dangerous: true),
      _AdvancedFlag(
          'kis_scheduler_sell_enabled', settings.kisSchedulerSellEnabled),
      _AdvancedFlag(
          'kis_scheduler_buy_enabled', settings.kisSchedulerBuyEnabled,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_allow_limited_auto_sell',
          settings.kisSchedulerAllowLimitedAutoSell),
      _AdvancedFlag('kis_scheduler_allow_limited_auto_buy',
          settings.kisSchedulerAllowLimitedAutoBuy,
          dangerous: true),
      _AdvancedFlag(
          'kis_live_auto_sell_enabled', settings.kisLiveAutoSellEnabled),
      _AdvancedFlag('kis_live_auto_buy_enabled', settings.kisLiveAutoBuyEnabled,
          dangerous: true),
      _AdvancedFlag(
          'kis_limited_auto_buy_enabled', settings.kisLimitedAutoBuyEnabled,
          dangerous: true),
    ];
    return SectionCard(
      padding: EdgeInsets.zero,
      child: ExpansionTile(
        initiallyExpanded: false,
        leading: const Icon(Icons.bug_report_outlined),
        title: const Text('Advanced Flags / Diagnostics'),
        childrenPadding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
        children: [
          _InfoRow(
            label: 'kr_no_new_entry_after',
            value: '${settings.krNoNewEntryAfter} KST',
            scope: 'KIS / KR',
          ),
          _InfoRow(
            label: 'no_new_entry_after',
            value: '${settings.noNewEntryAfter} (deprecated alias)',
            scope: 'KIS / KR',
          ),
          for (final flag in flags) _FlagLine(flag: flag),
          if (risk.riskyFlags.isNotEmpty)
            _InfoRow(
              label: 'risky_flags',
              value: risk.riskyFlags.join(', '),
              scope: 'KIS / KR',
            ),
          if (risk.blockingFlags.isNotEmpty)
            _InfoRow(
              label: 'blocking_flags',
              value: risk.blockingFlags.join(', '),
              scope: 'KIS / KR',
            ),
          _InfoRow(
            label: 'warning_level',
            value: risk.warningLevel,
            scope: 'KIS / KR',
          ),
        ],
      ),
    );
  }
}

class _StatusBanner extends StatelessWidget {
  const _StatusBanner({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.schedulerStatus;
    final risk = status.riskSummary;
    final warning = risk.warningLevel;
    final color = warning == 'dangerous_mixed'
        ? Colors.redAccent
        : warning == 'armed_sell_only'
            ? Colors.orangeAccent
            : warning == 'blocked'
                ? Colors.amberAccent
                : Colors.greenAccent;
    final message = status.warningMessage.isNotEmpty
        ? status.warningMessage
        : status.userFriendlySummary;
    return Container(
      key: Key('settings-warning-$warning'),
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
          _modeLabel(_currentMode(controller)),
          style: TextStyle(color: color, fontWeight: FontWeight.w900),
        ),
        if (status.userFriendlySummary.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(status.userFriendlySummary),
        ],
        if (message.isNotEmpty &&
            message.trim() != status.userFriendlySummary.trim()) ...[
          const SizedBox(height: 6),
          Text(message),
        ],
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _StatusChip(
            label: 'LIVE BUY ARMED',
            value: risk.liveBuyArmed,
            alert: risk.liveBuyArmed,
          ),
          _StatusChip(
            label: 'LIVE SELL ARMED',
            value: risk.liveSellArmed,
            alert: risk.liveSellArmed,
          ),
          _TextChip(
            label:
                'DAILY LIVE ORDER REMAINING ${risk.dailyLiveOrderRemaining?.toString() ?? 'n/a'}',
            color: color,
          ),
          _StatusChip(
            label: 'FULL LIVE TEST MODE',
            value: _currentMode(controller) == 'full_live_test_mode',
            alert: _currentMode(controller) == 'full_live_test_mode',
          ),
        ]),
      ]),
    );
  }
}

class _CardHeader extends StatelessWidget {
  const _CardHeader({
    required this.icon,
    required this.title,
    this.trailing,
  });

  final IconData icon;
  final String title;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Icon(icon, size: 20),
      const SizedBox(width: 8),
      Expanded(
        child: Text(title, style: Theme.of(context).textTheme.titleMedium),
      ),
      if (trailing != null) trailing!,
    ]);
  }
}

class _NumberField extends StatelessWidget {
  const _NumberField({
    required this.label,
    required this.scope,
    required this.controller,
    required this.onChanged,
    this.decimal = false,
  });

  final String label;
  final String scope;
  final TextEditingController controller;
  final VoidCallback onChanged;
  final bool decimal;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _ScopeChip(label: scope),
        TextField(
          controller: controller,
          keyboardType: TextInputType.numberWithOptions(decimal: decimal),
          onChanged: (_) => onChanged(),
          decoration: InputDecoration(labelText: label),
        ),
      ]),
    );
  }
}

class _ScopedTextField extends StatelessWidget {
  const _ScopedTextField({
    required this.scope,
    required this.label,
    required this.controller,
    required this.onChanged,
    this.helperText,
    this.suffixText,
  });

  final String scope;
  final String label;
  final TextEditingController controller;
  final VoidCallback onChanged;
  final String? helperText;
  final String? suffixText;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        _ScopeChip(label: scope),
        TextField(
          controller: controller,
          onChanged: (_) => onChanged(),
          decoration: InputDecoration(
            labelText: label,
            helperText: helperText,
            suffixText: suffixText,
          ),
        ),
      ]),
    );
  }
}

class _ScopedSwitchTile extends StatelessWidget {
  const _ScopedSwitchTile({
    required this.scope,
    required this.title,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });

  final String scope;
  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: Wrap(
        spacing: 8,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          _ScopeChip(label: scope),
          Text(title),
        ],
      ),
      subtitle: subtitle == null ? null : Text(subtitle!),
      value: value,
      onChanged: onChanged,
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value, this.scope});

  final String label;
  final String value;
  final String? scope;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 170,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
        if (scope != null) ...[
          _ScopeChip(label: scope!),
          const SizedBox(width: 8),
        ],
        Expanded(
          child: Text(
            value.isEmpty ? 'n/a' : value,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
        ),
      ]),
    );
  }
}

class _ScopeChip extends StatelessWidget {
  const _ScopeChip({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    final normalized = label.toUpperCase();
    final color = normalized.contains('KIS')
        ? Colors.orangeAccent
        : normalized.contains('ALPACA')
            ? Colors.lightBlueAccent
            : Colors.greenAccent;
    return _TextChip(label: normalized, color: color);
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({
    required this.label,
    required this.value,
    required this.alert,
  });

  final String label;
  final bool value;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    final color = alert ? Colors.redAccent : Colors.white70;
    return _TextChip(label: '$label ${value ? 'ON' : 'OFF'}', color: color);
  }
}

class _TextChip extends StatelessWidget {
  const _TextChip({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

class _SettingsChangeSummary extends StatelessWidget {
  const _SettingsChangeSummary({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final parts = text.split('|').map((item) => item.trim()).toList();
    return Wrap(spacing: 8, runSpacing: 8, children: [
      for (final part in parts)
        if (part.isNotEmpty)
          _TextChip(
            label: part,
            color: part.toLowerCase().contains('buy armed on')
                ? Colors.redAccent
                : Colors.lightBlueAccent,
          ),
    ]);
  }
}

class _PresetScopeDetails extends StatelessWidget {
  const _PresetScopeDetails({required this.mode});

  final String mode;

  @override
  Widget build(BuildContext context) {
    final scope = _presetScope(mode);
    final affects = _presetAffects(mode);
    final warning = _presetWarningLevel(mode);
    final color = warning == 'dangerous_mixed'
        ? Colors.redAccent
        : warning == 'armed_sell_only'
            ? Colors.orangeAccent
            : Colors.greenAccent;
    return Wrap(spacing: 8, runSpacing: 8, children: [
      _TextChip(label: 'Scope: $scope', color: color),
      _TextChip(label: 'Affects: $affects', color: color),
      _TextChip(label: 'Warning: $warning', color: color),
    ]);
  }
}

class _FlagLine extends StatelessWidget {
  const _FlagLine({required this.flag});

  final _AdvancedFlag flag;

  @override
  Widget build(BuildContext context) {
    final active = flag.value;
    final color = flag.dangerous && active ? Colors.redAccent : Colors.white70;
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(children: [
        _ScopeChip(label: _scopeForKey(flag.key)),
        const SizedBox(width: 8),
        Expanded(child: Text(flag.key)),
        _TextChip(label: active ? 'ON' : 'OFF', color: color),
      ]),
    );
  }
}

class _AdvancedFlag {
  const _AdvancedFlag(this.key, this.value, {this.dangerous = false});

  final String key;
  final bool value;
  final bool dangerous;
}

class _OperationModeOption {
  const _OperationModeOption(this.value, this.label, [this.description]);

  final String value;
  final String label;
  final String? description;
}

const _operationModeOptions = [
  _OperationModeOption('safe_mode', 'Safe Mode'),
  _OperationModeOption('dry_run_simulation', 'Dry-run Simulation'),
  _OperationModeOption('manual_live_trading', 'Manual Live Trading'),
  _OperationModeOption('kis_sell_only_automation', 'KIS Sell-only Automation'),
  _OperationModeOption(
    'full_live_test_mode',
    'Full Live Test Mode',
    'This enables live buy and live sell automation.',
  ),
];

Future<void> _applyMode(
  BuildContext context,
  DashboardController controller,
  String preset,
) async {
  var confirmDangerous = false;
  if (preset == 'full_live_test_mode') {
    final confirmed = await showConfirmActionDialog(
      context,
      title: 'Full Live Test Mode',
      description: 'This enables live buy and live sell automation.',
    );
    if (!confirmed) return;
    confirmDangerous = true;
  }
  final result = await controller.applyOperationModePreset(
    preset,
    confirmDangerous: confirmDangerous,
  );
  if (!context.mounted) return;
  _showResult(context, result);
}

Future<void> _saveSettings(
  BuildContext context,
  DashboardController controller,
  Map<String, dynamic> payload,
  String label,
) async {
  final result = await controller.updateKisAutomationSettings(
    payload,
    label: label,
  );
  if (!context.mounted) return;
  _showResult(context, result);
}

void _showResult(BuildContext context, ActionResult result) {
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(result.message),
    backgroundColor: result.success ? Colors.green : Colors.redAccent,
  ));
}

String _currentMode(DashboardController controller) {
  final statusMode = controller.schedulerStatus.currentOperationMode.trim();
  if (statusMode.isNotEmpty) return statusMode;
  return controller.settings.currentOperationMode;
}

String _modeLabel(String mode) {
  switch (mode) {
    case 'safe_mode':
      return 'Safe Mode';
    case 'dry_run_simulation':
      return 'Dry-run Simulation';
    case 'manual_live_trading':
      return 'Manual Live Trading';
    case 'kis_sell_only_automation':
      return 'KIS Sell-only Automation';
    case 'full_live_test_mode':
      return 'Full Live Test Mode';
  }
  return 'Custom Mode';
}

String _presetScope(String mode) {
  switch (mode) {
    case 'kis_sell_only_automation':
    case 'full_live_test_mode':
      return 'KIS / KR';
    default:
      return 'Global';
  }
}

String _presetAffects(String mode) {
  switch (mode) {
    case 'kis_sell_only_automation':
      return 'KIS scheduler sell only';
    case 'full_live_test_mode':
      return 'KIS scheduler live buy + sell';
    case 'manual_live_trading':
      return 'Manual trading; scheduler live orders off';
    default:
      return 'Alpaca + KIS';
  }
}

String _presetWarningLevel(String mode) {
  switch (mode) {
    case 'kis_sell_only_automation':
      return 'armed_sell_only';
    case 'full_live_test_mode':
      return 'dangerous_mixed';
    default:
      return 'safe';
  }
}

String _scopeForKey(String key) {
  if (key.startsWith('kis_') || key.startsWith('kr_')) {
    return 'KIS / KR';
  }
  if (key.startsWith('us_') || key.startsWith('alpaca_')) {
    return 'ALPACA / US';
  }
  return 'GLOBAL';
}

String _krModeSummary(dynamic settings) {
  if (!settings.kisSchedulerEnabled) return 'Safe';
  if (settings.kisSchedulerDryRun && !settings.kisSchedulerLiveEnabled) {
    return 'Dry-run';
  }
  final buy = settings.kisSchedulerBuyEnabled ||
      settings.kisSchedulerAllowLimitedAutoBuy ||
      settings.kisLiveAutoBuyEnabled ||
      settings.kisLimitedAutoBuyEnabled;
  if (settings.kisSchedulerLiveEnabled && buy) return 'Full live test';
  if (settings.kisSchedulerLiveEnabled && settings.kisSchedulerSellEnabled) {
    return 'Sell-only live';
  }
  return 'Safe';
}

String _nextRun(dynamic marketStatus) {
  final name = marketStatus.nextSlotName;
  final time = marketStatus.nextSlotTimeLocal;
  if (name == null && time == null) return 'n/a';
  if (name == null) return time ?? 'n/a';
  if (time == null) return name;
  return '$name $time';
}

int? _intValue(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) return null;
  return int.tryParse(trimmed);
}

double? _percentValue(String value) {
  final trimmed = value.trim();
  if (trimmed.isEmpty) return null;
  final parsed = double.tryParse(trimmed);
  if (parsed == null) return null;
  return parsed > 1 ? parsed / 100 : parsed;
}

String _formatPercentInput(double value) {
  return (value * 100).toStringAsFixed(2);
}
