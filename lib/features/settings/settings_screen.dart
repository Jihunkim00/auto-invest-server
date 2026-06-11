import 'package:flutter/material.dart';

import '../../core/widgets/confirm_action_dialog.dart';
import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import 'widgets/safety_settings_section.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text(
                    'Settings',
                    style: TextStyle(fontSize: 28, fontWeight: FontWeight.w700),
                  ),
                ),
                BrokerContextBadge(controller: controller),
              ]),
              const SizedBox(height: 6),
              Text(
                controller.selectedProvider == SelectedProvider.kis
                    ? 'KIS safety and manual live status.'
                    : 'Alpaca paper and common safety status.',
                style: const TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 12),
              _OperationModeCard(controller: controller),
              const SizedBox(height: 12),
              _ScheduleControlCard(controller: controller),
              const SizedBox(height: 12),
              _RiskLimitsCard(controller: controller),
              const SizedBox(height: 12),
              _ExitRulesCard(controller: controller),
              const SizedBox(height: 12),
              _AdvancedFlagsCard(controller: controller),
              const SizedBox(height: 12),
              SafetySettingsSection(controller: controller),
            ],
          ),
        );
      },
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
          title: 'Operation Mode',
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
        DropdownButtonFormField<String>(
          key: ValueKey('operation-mode-$mode'),
          initialValue: _operationModeOptions.any((option) => option.value == mode)
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
        if (mode == 'full_live_test_mode') ...[
          const SizedBox(height: 6),
          const Text(
            'This enables live buy and live sell automation.',
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

class _ScheduleControlCard extends StatelessWidget {
  const _ScheduleControlCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final status = controller.schedulerStatus;
    final loading = controller.kisAutomationSettingsLoading;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const _CardHeader(
          icon: Icons.calendar_month_outlined,
          title: 'Schedule Control',
        ),
        const SizedBox(height: 8),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Scheduler ON/OFF'),
          value: settings.schedulerEnabled,
          onChanged: loading
              ? null
              : (value) => _saveSettings(
                    context,
                    controller,
                    {'scheduler_enabled': value},
                    'Scheduler',
                  ),
        ),
        _InfoRow(
          label: 'US schedule enabled',
          value: status.us.enabledForScheduler ? 'ON' : 'OFF',
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('KR schedule enabled'),
          value: settings.kisSchedulerEnabled,
          onChanged: loading
              ? null
              : (value) => _saveSettings(
                    context,
                    controller,
                    {'kr_scheduler_enabled': value},
                    'KR schedule',
                  ),
        ),
        _InfoRow(label: 'Next US run', value: _nextRun(status.us)),
        _InfoRow(label: 'Next KR run', value: _nextRun(status.kr)),
        _InfoRow(label: 'KR mode summary', value: _krModeSummary(settings)),
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
  final _noNewEntryAfter = TextEditingController();
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
    _noNewEntryAfter.dispose();
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
          controller: _maxTrades,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max live orders per day',
          controller: _maxLiveOrders,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max positions',
          controller: _maxPositions,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max order notional %',
          controller: _maxOrderNotionalPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Max position %',
          controller: _maxPositionPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        _NumberField(
          label: 'Daily max loss %',
          controller: _dailyMaxLossPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        TextField(
          controller: _noNewEntryAfter,
          onChanged: (_) => _markEditing(),
          decoration: const InputDecoration(labelText: 'No new entry after'),
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
      settings.noNewEntryAfter,
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
    _noNewEntryAfter.text = settings.noNewEntryAfter;
  }

  Future<void> _save() async {
    final payload = <String, dynamic>{
      'max_trades_per_day': _intValue(_maxTrades.text),
      'max_live_orders_per_day': _intValue(_maxLiveOrders.text),
      'max_positions': _intValue(_maxPositions.text),
      'max_order_notional_pct': _percentValue(_maxOrderNotionalPct.text),
      'max_position_pct': _percentValue(_maxPositionPct.text),
      'daily_max_loss_pct': _percentValue(_dailyMaxLossPct.text),
      'no_new_entry_after': _noNewEntryAfter.text.trim(),
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
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Stop-loss enabled'),
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
          controller: _stopLossPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        SwitchListTile(
          contentPadding: EdgeInsets.zero,
          title: const Text('Take-profit enabled'),
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
          controller: _takeProfitPct,
          decimal: true,
          onChanged: _markEditing,
        ),
        if (_takeProfitEnabled &&
            (risk.liveSellArmed || widget.controller.settings.kisSchedulerLiveEnabled))
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
      _AdvancedFlag('kis_scheduler_live_enabled',
          settings.kisSchedulerLiveEnabled,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_allow_real_orders',
          settings.kisSchedulerAllowRealOrders,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_configured_allow_real_orders',
          settings.kisSchedulerConfiguredAllowRealOrders,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_sell_enabled',
          settings.kisSchedulerSellEnabled),
      _AdvancedFlag('kis_scheduler_buy_enabled',
          settings.kisSchedulerBuyEnabled,
          dangerous: true),
      _AdvancedFlag('kis_scheduler_allow_limited_auto_sell',
          settings.kisSchedulerAllowLimitedAutoSell),
      _AdvancedFlag('kis_scheduler_allow_limited_auto_buy',
          settings.kisSchedulerAllowLimitedAutoBuy,
          dangerous: true),
      _AdvancedFlag('kis_live_auto_sell_enabled',
          settings.kisLiveAutoSellEnabled),
      _AdvancedFlag('kis_live_auto_buy_enabled',
          settings.kisLiveAutoBuyEnabled,
          dangerous: true),
      _AdvancedFlag('kis_limited_auto_buy_enabled',
          settings.kisLimitedAutoBuyEnabled,
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
          for (final flag in flags) _FlagLine(flag: flag),
          if (risk.riskyFlags.isNotEmpty)
            _InfoRow(label: 'risky_flags', value: risk.riskyFlags.join(', ')),
          if (risk.blockingFlags.isNotEmpty)
            _InfoRow(
              label: 'blocking_flags',
              value: risk.blockingFlags.join(', '),
            ),
          _InfoRow(label: 'warning_level', value: risk.warningLevel),
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
    required this.controller,
    required this.onChanged,
    this.decimal = false,
  });

  final String label;
  final TextEditingController controller;
  final VoidCallback onChanged;
  final bool decimal;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      keyboardType: TextInputType.numberWithOptions(decimal: decimal),
      onChanged: (_) => onChanged(),
      decoration: InputDecoration(labelText: label),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 170,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
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
