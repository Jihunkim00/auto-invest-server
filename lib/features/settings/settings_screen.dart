import 'package:flutter/material.dart';

import '../../core/widgets/confirm_action_dialog.dart';
import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import 'widgets/operation_toggle_card.dart';
import 'widgets/safety_settings_section.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final s = controller.settings;
        return SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Expanded(
                  child: Text('Settings',
                      style:
                          TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
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
              const SizedBox(height: 10),
              const _SectionTitle('Safety Mode'),
              OperationToggleCard(
                title: 'Dry Run',
                subtitle:
                    'Safety mode. Keep enabled for paper-only validation.',
                value: s.dryRun,
                loading: controller.dryRunLoading,
                onChanged: (v) async {
                  if (!v) {
                    final ok = await showConfirmActionDialog(context,
                        title: 'Turn Dry Run OFF?',
                        description:
                            'This reduces safety. Confirm only if backend policy allows it.');
                    if (!ok) return;
                  }
                  final result = await controller.setDryRun(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              OperationToggleCard(
                title: 'Kill Switch',
                subtitle:
                    'Emergency block. ON blocks trading actions in backend.',
                value: s.killSwitch,
                loading: controller.killSwitchLoading,
                onChanged: (v) async {
                  if (!v) {
                    final ok = await showConfirmActionDialog(context,
                        title: 'Turn Kill Switch OFF?',
                        description: 'This removes emergency halt protection.');
                    if (!ok) return;
                  }
                  final result = await controller.toggleKillSwitch(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              const SizedBox(height: 12),
              if (controller.selectedProvider == SelectedProvider.kis) ...[
                const _SectionTitle('KIS Automation Controls'),
                _KisAutomationControlsCard(controller: controller),
                const SizedBox(height: 12),
                const _SectionTitle('KIS Runtime Diagnostics'),
                _RuntimeDiagnosticsCard(controller: controller),
              ] else ...[
                const _SectionTitle('Trading Permissions'),
                _RuntimeDiagnosticsCard(controller: controller),
              ],
              const SizedBox(height: 12),
              const _SectionTitle('Automation Status'),
              OperationToggleCard(
                title: 'Scheduler Enabled',
                subtitle:
                    'Controls scheduled checks through backend scheduler_enabled. Real-order permission is read-only below.',
                value: s.schedulerEnabled,
                loading: controller.schedulerLoading,
                onChanged: (v) async {
                  final result = await controller.toggleScheduler(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              OperationToggleCard(
                title: 'Bot Enabled',
                subtitle:
                    'Enables backend bot orchestration. Does not place orders directly from app.',
                value: s.botEnabled,
                loading: controller.botLoading,
                onChanged: (v) async {
                  if (v) {
                    final ok = await showConfirmActionDialog(context,
                        title: 'Turn Bot ON?',
                        description: 'Confirm enabling bot control mode.');
                    if (!ok) return;
                  }
                  final result = await controller.toggleBot(v);
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
              ),
              const SizedBox(height: 12),
              const _SectionTitle('Runtime Status'),
              SafetySettingsSection(controller: controller),
            ],
          ),
        );
      },
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Text(
        text,
        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _KisAutomationControlsCard extends StatelessWidget {
  const _KisAutomationControlsCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final s = controller.settings;
    final loading = controller.kisAutomationSettingsLoading;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.tune, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'KIS Automation Controls',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          if (loading)
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
        ]),
        const SizedBox(height: 8),
        const Text(
          'These switches update /ops/settings. Backend safety gates still decide whether any real KIS order can be submitted.',
          style: TextStyle(color: Colors.white70),
        ),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          FilledButton.icon(
            onPressed: loading
                ? null
                : () => _applyPreset(
                      context,
                      controller: controller,
                      title: 'Return to Safe Mode',
                      payload: _safeModePayload,
                      strongWarning: false,
                    ),
            icon: const Icon(Icons.health_and_safety_outlined),
            label: const Text('Return to Safe Mode'),
          ),
          OutlinedButton.icon(
            onPressed: loading
                ? null
                : () => _applyPreset(
                      context,
                      controller: controller,
                      title: 'Enable KIS Sell-Only Test Mode',
                      payload: _kisSellOnlyTestModePayload,
                      strongWarning: true,
                    ),
            icon: const Icon(Icons.warning_amber_outlined),
            label: const Text('Enable KIS Sell-Only Test Mode'),
          ),
        ]),
        if (controller.latestSettingsChangeSummary != null) ...[
          const SizedBox(height: 12),
          _SettingsChangeSummary(text: controller.latestSettingsChangeSummary!),
        ],
        const Divider(height: 24),
        _KisAutomationSwitch(
          title: 'KIS Scheduler Enabled',
          subtitle: 'Controls kis_scheduler_enabled.',
          value: s.kisSchedulerEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {'kis_scheduler_enabled': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'KIS Scheduler Dry Run',
          subtitle:
              'Keep ON unless intentionally allowing live scheduler mode.',
          value: s.kisSchedulerDryRun,
          loading: loading,
          confirmationWhen: (value) => !value,
          payloadFor: (value) => {'kis_scheduler_dry_run': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'KIS Scheduler Real Orders',
          subtitle:
              'Updates kis_scheduler_allow_real_orders and configured_allow_real_orders together.',
          value: s.kisSchedulerAllowRealOrders ||
              s.kisSchedulerConfiguredAllowRealOrders,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {
            'kis_scheduler_allow_real_orders': value,
            'kis_scheduler_configured_allow_real_orders': value,
          },
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'KIS Scheduler Sell Enabled',
          subtitle: 'Allows guarded scheduler sell checks to proceed.',
          value: s.kisSchedulerSellEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {'kis_scheduler_sell_enabled': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'KIS Scheduler Buy Enabled',
          subtitle:
              'Buy automation remains gated by backend sell-priority checks.',
          value: s.kisSchedulerBuyEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {'kis_scheduler_buy_enabled': value},
          controller: controller,
          strongWarning: true,
        ),
        _KisAutomationSwitch(
          title: 'KIS Live Auto Sell',
          subtitle:
              'Enables live auto-sell permission after all backend gates pass.',
          value: s.kisLiveAutoSellEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {'kis_live_auto_sell_enabled': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'KIS Live Auto Buy',
          subtitle:
              'Enables live auto-buy permission after all backend gates pass.',
          value: s.kisLiveAutoBuyEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {'kis_live_auto_buy_enabled': value},
          controller: controller,
          strongWarning: true,
        ),
        _KisAutomationSwitch(
          title: 'Stop-loss Auto Sell',
          subtitle:
              'Keeps canonical and sell-prefixed stop-loss aliases synced.',
          value: s.kisLimitedAutoStopLossEnabled ||
              s.kisLimitedAutoSellStopLossEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {
            'kis_limited_auto_stop_loss_enabled': value,
            'kis_limited_auto_sell_stop_loss_enabled': value,
          },
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'Take-profit Auto Sell',
          subtitle:
              'Keeps take-profit aliases and the take-profit trigger flag synced.',
          value: s.kisLimitedAutoTakeProfitEnabled ||
              s.kisLimitedAutoSellTakeProfitEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {
            'kis_limited_auto_take_profit_enabled': value,
            'kis_limited_auto_sell_take_profit_enabled': value,
            'kis_limited_auto_sell_allow_take_profit_trigger': value,
          },
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'Limited Auto Buy',
          subtitle: 'Enables the limited auto-buy executor permission.',
          value: s.kisLimitedAutoBuyEnabled,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) => {'kis_limited_auto_buy_enabled': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'Limited Auto Buy Shadow Review Required',
          subtitle: 'Keep ON so buy execution requires shadow review first.',
          value: s.kisLimitedAutoBuyRequiresShadowReview,
          loading: loading,
          confirmationWhen: (value) => !value,
          payloadFor: (value) =>
              {'kis_limited_auto_buy_requires_shadow_review': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'Scheduler Allow Limited Auto Sell',
          subtitle: 'Allows scheduler guarded sell to call limited auto-sell.',
          value: s.kisSchedulerAllowLimitedAutoSell,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) =>
              {'kis_scheduler_allow_limited_auto_sell': value},
          controller: controller,
        ),
        _KisAutomationSwitch(
          title: 'Scheduler Allow Limited Auto Buy',
          subtitle: 'Allows scheduler guarded buy to call limited auto-buy.',
          value: s.kisSchedulerAllowLimitedAutoBuy,
          loading: loading,
          confirmationWhen: (value) => value,
          payloadFor: (value) =>
              {'kis_scheduler_allow_limited_auto_buy': value},
          controller: controller,
        ),
      ]),
    );
  }
}

class _KisAutomationSwitch extends StatelessWidget {
  const _KisAutomationSwitch({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.loading,
    required this.confirmationWhen,
    required this.payloadFor,
    required this.controller,
    this.strongWarning = false,
  });

  final String title;
  final String subtitle;
  final bool value;
  final bool loading;
  final bool Function(bool value) confirmationWhen;
  final Map<String, dynamic> Function(bool value) payloadFor;
  final DashboardController controller;
  final bool strongWarning;

  @override
  Widget build(BuildContext context) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(title),
      subtitle: Text(subtitle),
      value: value,
      onChanged: loading
          ? null
          : (nextValue) async {
              if (confirmationWhen(nextValue)) {
                final confirmed = await _confirmKisSettingChange(
                  context,
                  title: title,
                  currentValue: value,
                  newValue: nextValue,
                  strongWarning: strongWarning,
                );
                if (!confirmed) return;
              }
              final result = await controller.updateKisAutomationSettings(
                payloadFor(nextValue),
                label: title,
              );
              if (!context.mounted) return;
              ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                content: Text(result.message),
                backgroundColor:
                    result.success ? Colors.green : Colors.redAccent,
              ));
            },
    );
  }
}

class _SettingsChangeSummary extends StatelessWidget {
  const _SettingsChangeSummary({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final parts = text.split('|').map((item) => item.trim()).toList();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border:
            Border.all(color: Colors.lightBlueAccent.withValues(alpha: 0.24)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text(
          'Settings Change Result',
          style: TextStyle(
            color: Colors.lightBlueAccent,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final part in parts)
            if (part.isNotEmpty)
              _SummaryBadge(
                text: part,
                color: part.endsWith('ON') &&
                        !part.startsWith('dry_run') &&
                        !part.startsWith('KIS scheduler') &&
                        !part.startsWith('KIS sell') &&
                        !part.startsWith('stop-loss') &&
                        !part.startsWith('take-profit')
                    ? Colors.orangeAccent
                    : Colors.white70,
              ),
        ]),
      ]),
    );
  }
}

class _SummaryBadge extends StatelessWidget {
  const _SummaryBadge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.28)),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

Future<bool> _confirmKisSettingChange(
  BuildContext context, {
  required String title,
  required bool currentValue,
  required bool newValue,
  bool strongWarning = false,
}) {
  return showConfirmActionDialog(
    context,
    title: '${strongWarning ? 'Strong confirmation: ' : ''}$title',
    description: '$title\n${_onOff(currentValue)} -> ${_onOff(newValue)}\n\n'
        'This may allow real KIS orders when all backend gates pass.',
  );
}

Future<void> _applyPreset(
  BuildContext context, {
  required DashboardController controller,
  required String title,
  required Map<String, dynamic> payload,
  required bool strongWarning,
}) async {
  final confirmed = await showConfirmActionDialog(
    context,
    title: '${strongWarning ? 'Strong confirmation: ' : ''}$title',
    description: strongWarning
        ? '$title\n\nThis may allow real KIS orders when all backend gates pass.'
        : '$title\n\nThis returns KIS automation controls to a safer runtime mode.',
  );
  if (!confirmed) return;
  final result = await controller.updateKisAutomationSettings(
    payload,
    label: title,
  );
  if (!context.mounted) return;
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
    content: Text(result.message),
    backgroundColor: result.success ? Colors.green : Colors.redAccent,
  ));
}

String _onOff(bool value) => value ? 'ON' : 'OFF';

const Map<String, dynamic> _kisSellOnlyTestModePayload = {
  'dry_run': false,
  'kill_switch': false,
  'scheduler_enabled': true,
  'kis_scheduler_enabled': true,
  'kis_scheduler_dry_run': false,
  'kis_scheduler_allow_real_orders': true,
  'kis_scheduler_configured_allow_real_orders': true,
  'kis_scheduler_sell_enabled': true,
  'kis_live_auto_sell_enabled': true,
  'kis_limited_auto_stop_loss_enabled': true,
  'kis_limited_auto_sell_stop_loss_enabled': true,
  'kis_limited_auto_take_profit_enabled': true,
  'kis_limited_auto_sell_take_profit_enabled': true,
  'kis_limited_auto_sell_allow_take_profit_trigger': true,
  'kis_scheduler_buy_enabled': false,
  'kis_live_auto_buy_enabled': false,
  'kis_limited_auto_buy_enabled': false,
  'kis_scheduler_allow_limited_auto_buy': false,
  'kis_scheduler_allow_limited_auto_sell': true,
};

const Map<String, dynamic> _safeModePayload = {
  'dry_run': true,
  'kill_switch': false,
  'scheduler_enabled': true,
  'kis_scheduler_enabled': false,
  'kis_scheduler_dry_run': true,
  'kis_scheduler_allow_real_orders': false,
  'kis_scheduler_configured_allow_real_orders': false,
  'kis_scheduler_sell_enabled': false,
  'kis_scheduler_buy_enabled': false,
  'kis_live_auto_sell_enabled': false,
  'kis_live_auto_buy_enabled': false,
  'kis_limited_auto_stop_loss_enabled': false,
  'kis_limited_auto_sell_stop_loss_enabled': false,
  'kis_limited_auto_take_profit_enabled': false,
  'kis_limited_auto_sell_take_profit_enabled': false,
  'kis_limited_auto_sell_allow_take_profit_trigger': false,
  'kis_limited_auto_buy_enabled': false,
  'kis_scheduler_allow_limited_auto_buy': false,
  'kis_scheduler_allow_limited_auto_sell': false,
};

class _RuntimeDiagnosticsCard extends StatelessWidget {
  const _RuntimeDiagnosticsCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final settings = controller.settings;
    final safety = controller.kisSafetyStatus;
    final scheduler = controller.schedulerStatus.kr;
    final isKis = controller.selectedProvider == SelectedProvider.kis;
    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.lock_outline, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              isKis
                  ? 'KIS Runtime Diagnostics'
                  : 'Alpaca paper permission flags',
              style: Theme.of(context).textTheme.titleMedium,
            ),
          ),
          const _ReadOnlyBadge(),
        ]),
        const SizedBox(height: 10),
        if (isKis) ...[
          _PermissionLine(
            label: 'KIS real order',
            value:
                safety.kisRealOrderEnabled ? 'Allowed by runtime' : 'Disabled',
            alert: safety.kisRealOrderEnabled,
          ),
          _PermissionLine(
            label: 'KIS live auto buy',
            value: settings.kisLiveAutoBuyEnabled ? 'Enabled' : 'Disabled',
            alert: settings.kisLiveAutoBuyEnabled,
          ),
          _PermissionLine(
            label: 'KIS live auto sell',
            value: settings.kisLiveAutoSellEnabled ? 'Enabled' : 'Disabled',
            alert: settings.kisLiveAutoSellEnabled,
          ),
          _PermissionLine(
            label: 'Scheduler real orders',
            value: scheduler.realOrdersAllowed ||
                    settings.kisSchedulerAllowRealOrders
                ? 'Allowed'
                : 'Disabled',
            alert: scheduler.realOrdersAllowed ||
                settings.kisSchedulerAllowRealOrders,
          ),
          _PermissionLine(
            label: 'Manual confirmation',
            value: settings.kisLiveAutoRequiresManualConfirm
                ? 'Required'
                : 'Not required',
            alert: !settings.kisLiveAutoRequiresManualConfirm,
          ),
        ] else ...[
          _PermissionLine(
            label: 'Alpaca mode',
            value: 'Paper trading',
            alert: false,
          ),
          _PermissionLine(
            label: 'Broker mode',
            value: settings.brokerMode,
            alert: false,
          ),
          _PermissionLine(
            label: 'US scheduler',
            value: controller.schedulerStatus.us.enabledForScheduler
                ? 'Enabled for checks'
                : 'Disabled',
            alert: false,
          ),
        ],
      ]),
    );
  }
}

class _PermissionLine extends StatelessWidget {
  const _PermissionLine({
    required this.label,
    required this.value,
    required this.alert,
  });

  final String label;
  final String value;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 7),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 150,
          child: Text(label, style: const TextStyle(color: Colors.white54)),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: alert ? Colors.redAccent : Colors.greenAccent,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
        const SizedBox(width: 8),
        const _ReadOnlyBadge(),
      ]),
    );
  }
}

class _ReadOnlyBadge extends StatelessWidget {
  const _ReadOnlyBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
      ),
      child: const Text(
        'READ-ONLY',
        style: TextStyle(
          color: Colors.white70,
          fontSize: 10,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}
