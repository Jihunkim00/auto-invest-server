import 'package:flutter/material.dart';

import '../../../core/i18n/app_strings.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/automation_mode_control.dart';
import '../../dashboard/dashboard_controller.dart';

const _automationModes = [
  'off',
  'monitor_only',
  'dry_run_auto',
  'phase1_live_ready',
];

class AutomationModeControlPanel extends StatefulWidget {
  const AutomationModeControlPanel({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<AutomationModeControlPanel> createState() =>
      _AutomationModeControlPanelState();
}

class _AutomationModeControlPanelState
    extends State<AutomationModeControlPanel> {
  final _reasonController = TextEditingController();
  String _selectedMode = 'off';
  String? _lastSyncedMode;
  bool _acknowledged = false;

  @override
  void dispose() {
    _reasonController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        final controller = widget.controller;
        final strings = controller.strings;
        final status = controller.automationModeStatus;
        _syncSelection(status);
        final loading = controller.automationModeLoading;
        final ackRequired = _requiresAcknowledgement(_selectedMode);
        return SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(
                    Icons.tune_outlined,
                    color: Colors.lightBlueAccent,
                    size: 22,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          strings.automationModeControl,
                          style: const TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          strings.automationModeControlSubtitle,
                          style: const TextStyle(color: Colors.white70),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    key: const ValueKey('automation-mode-refresh-button'),
                    tooltip: strings.refresh,
                    onPressed: loading ? null : () => _refresh(context),
                    icon: loading
                        ? const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          )
                        : const Icon(Icons.refresh),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _SafetyBadges(strings: strings),
              const SizedBox(height: 12),
              if (controller.automationModeError != null) ...[
                Text(
                  controller.automationModeError!,
                  style: const TextStyle(color: Colors.orangeAccent),
                ),
                const SizedBox(height: 10),
              ],
              if (status == null)
                _EmptyStatus(strings: strings)
              else ...[
                _ModeSummary(status: status, strings: strings),
                const SizedBox(height: 12),
                _ReasonBlocks(status: status, strings: strings),
                const SizedBox(height: 12),
                _GateBlock(status: status, strings: strings),
                const SizedBox(height: 12),
                _ModuleBlock(status: status, strings: strings),
              ],
              const SizedBox(height: 14),
              Text(
                strings.selectAutomationMode,
                style: const TextStyle(fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 8),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final mode in _automationModes)
                    ChoiceChip(
                      key: ValueKey('automation-mode-option-$mode'),
                      label: Text(strings.automationModeLabel(mode)),
                      selected: _selectedMode == mode,
                      onSelected: loading
                          ? null
                          : (selected) {
                              if (!selected) return;
                              setState(() {
                                _selectedMode = mode;
                                _acknowledged = false;
                              });
                            },
                    ),
                ],
              ),
              const SizedBox(height: 12),
              TextField(
                key: const ValueKey('automation-mode-reason-field'),
                controller: _reasonController,
                minLines: 1,
                maxLines: 3,
                decoration: InputDecoration(
                  labelText: strings.optionalReason,
                  border: const OutlineInputBorder(),
                ),
              ),
              if (ackRequired) ...[
                const SizedBox(height: 8),
                CheckboxListTile(
                  key: const ValueKey('automation-mode-risk-ack-checkbox'),
                  contentPadding: EdgeInsets.zero,
                  value: _acknowledged,
                  controlAffinity: ListTileControlAffinity.leading,
                  onChanged: loading
                      ? null
                      : (value) {
                          setState(() => _acknowledged = value ?? false);
                        },
                  title: Text(strings.operatorRiskAcknowledgement),
                  subtitle: Text(strings.acknowledgementRequiredForMode),
                ),
              ],
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  FilledButton.icon(
                    key: const ValueKey('automation-mode-apply-button'),
                    onPressed: loading || (ackRequired && !_acknowledged)
                        ? null
                        : () => _apply(context),
                    icon: const Icon(Icons.verified_user_outlined, size: 18),
                    label: Text(strings.changeWithRiskAcknowledgement),
                  ),
                  OutlinedButton.icon(
                    key: const ValueKey('automation-mode-off-button'),
                    onPressed: loading ? null : () => _turnOff(context),
                    icon: const Icon(Icons.power_settings_new, size: 18),
                    label: Text(strings.turnOffAutomation),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  void _syncSelection(AutomationModeControlStatus? status) {
    if (status == null || status.automationMode == _lastSyncedMode) return;
    _selectedMode = status.automationMode;
    _lastSyncedMode = status.automationMode;
    _acknowledged = false;
  }

  Future<void> _refresh(BuildContext context) async {
    final result = await widget.controller.refreshAutomationModeStatus();
    if (!context.mounted) return;
    _showSnack(context, result);
  }

  Future<void> _apply(BuildContext context) async {
    final result = await widget.controller.setAutomationMode(
      automationMode: _selectedMode,
      reason: _reasonController.text,
      operatorAcknowledgedRisks: _acknowledged,
    );
    if (!context.mounted) return;
    _showSnack(context, result);
  }

  Future<void> _turnOff(BuildContext context) async {
    final result = await widget.controller.turnOffAutomationMode(
      reason: _reasonController.text,
    );
    if (!context.mounted) return;
    _showSnack(context, result);
  }

  void _showSnack(BuildContext context, ActionResult result) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(result.message),
        backgroundColor: result.success ? Colors.green : Colors.redAccent,
      ),
    );
  }
}

class _SafetyBadges extends StatelessWidget {
  const _SafetyBadges({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 6,
      runSpacing: 6,
      children: [
        _Badge(label: strings.disabledByDefault),
        _Badge(label: strings.noBrokerSubmitModeControl),
        _Badge(label: strings.independentSafetyGatesRequired),
      ],
    );
  }
}

class _EmptyStatus extends StatelessWidget {
  const _EmptyStatus({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return _Banner(
      icon: Icons.lock_outline,
      label: strings.automationModeNotLoaded,
      detail: strings.liveOrdersRemainBlocked,
      color: Colors.white70,
    );
  }
}

class _ModeSummary extends StatelessWidget {
  const _ModeSummary({required this.status, required this.strings});

  final AutomationModeControlStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final color = status.liveEligible
        ? Colors.greenAccent
        : status.liveBlocked
            ? Colors.orangeAccent
            : Colors.lightBlueAccent;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _Banner(
          icon: status.liveEligible
              ? Icons.task_alt
              : Icons.admin_panel_settings_outlined,
          label: strings.liveOrderEligibility,
          detail: status.liveEligible ? strings.ready : strings.blocked,
          color: color,
        ),
        const SizedBox(height: 10),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _Metric(
              label: strings.currentMode,
              value: status.modeLabel,
            ),
            _Metric(
              label: strings.effectiveStatus,
              value: strings.automationControlLabel(status.effectiveStatus),
              valueColor: color,
            ),
            _Metric(
              label: strings.productionReadiness,
              value: strings.readinessStatusLabel(
                status.productionReadinessStatus,
              ),
            ),
            _Metric(
              label: strings.ordersRemaining,
              value: '${status.dailyTradeLimitRemaining}',
            ),
          ],
        ),
        if (status.modeUpdatedAt != null) ...[
          const SizedBox(height: 8),
          _Line(
            label: strings.modeUpdated,
            value: formatTimestampWithKst(
              status.modeUpdatedAt!.toIso8601String(),
            ),
          ),
        ],
        if (status.modeReason != null) ...[
          const SizedBox(height: 4),
          _Line(label: strings.reason, value: status.modeReason!),
        ],
      ],
    );
  }
}

class _ReasonBlocks extends StatelessWidget {
  const _ReasonBlocks({required this.status, required this.strings});

  final AutomationModeControlStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _ReasonList(
          title: strings.blockingReasons,
          items: status.blockingReasons,
          color: Colors.orangeAccent,
          strings: strings,
        ),
        const SizedBox(height: 8),
        _ReasonList(
          title: strings.warningReasons,
          items: status.warningReasons,
          color: Colors.amberAccent,
          strings: strings,
        ),
        const SizedBox(height: 8),
        _Line(
          label: strings.nextSafeAction,
          value: strings.automationControlLabel(status.nextSafeAction),
          valueColor: Colors.lightBlueAccent,
        ),
      ],
    );
  }
}

class _GateBlock extends StatelessWidget {
  const _GateBlock({required this.status, required this.strings});

  final AutomationModeControlStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          strings.independentSafetyGatesRequired,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _GateTile(
              label: strings.dryRunIsSeparate,
              value: status.dryRun ? strings.enabled : strings.disabled,
              active: status.dryRun,
            ),
            _GateTile(
              label: strings.killSwitchIsSeparate,
              value: status.killSwitch ? strings.enabled : strings.disabled,
              active: status.killSwitch,
            ),
            _GateTile(
              label: strings.kisRealOrdersAreSeparate,
              value: status.kisRealOrderEnabled
                  ? strings.enabled
                  : strings.disabled,
              active: status.kisRealOrderEnabled,
            ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          strings.liveOrdersRemainBlocked,
          style: const TextStyle(color: Colors.white60, fontSize: 12),
        ),
      ],
    );
  }
}

class _ModuleBlock extends StatelessWidget {
  const _ModuleBlock({required this.status, required this.strings});

  final AutomationModeControlStatus status;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          strings.automationModeModules,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          runSpacing: 8,
          children: [
            _ModuleTile(
              label: strings.portfolioOrchestrator,
              enabled: status.portfolioOrchestratorEnabled,
              detail: status.portfolioOrchestratorAllowLiveOrders
                  ? strings.liveOrdersAllowed
                  : strings.noLiveOrders,
            ),
            _ModuleTile(
              label: strings.positionManagementDryRun,
              enabled: status.positionManagementSchedulerEnabled,
              detail: strings.dryRunOnly,
            ),
            _ModuleTile(
              label: strings.autoBuyPhase1,
              enabled: status.autoBuyLivePhase1Enabled,
              detail: strings.limitedLiveAutoBuy,
            ),
            _ModuleTile(
              label: strings.autoSellPhase1,
              enabled: status.autoSellLivePhase1Enabled,
              detail: strings.limitedLiveAutoSell,
            ),
            _ModuleTile(
              label: strings.scheduler,
              enabled: status.schedulerEnabled,
              detail: strings.schedulerSafety,
            ),
          ],
        ),
      ],
    );
  }
}

class _ReasonList extends StatelessWidget {
  const _ReasonList({
    required this.title,
    required this.items,
    required this.color,
    required this.strings,
  });

  final String title;
  final List<String> items;
  final Color color;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            title,
            style: TextStyle(color: color, fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 6),
          if (items.isEmpty)
            Text(strings.none, style: const TextStyle(color: Colors.white60))
          else
            for (final item in items)
              Padding(
                padding: const EdgeInsets.only(bottom: 3),
                child: Text(
                  strings.automationControlLabel(item),
                  style: const TextStyle(color: Colors.white70),
                ),
              ),
        ],
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({
    required this.icon,
    required this.label,
    required this.detail,
    required this.color,
  });

  final IconData icon;
  final String label;
  final String detail;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  detail,
                  style: TextStyle(
                    color: color,
                    fontSize: 18,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800),
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 180,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: valueColor ?? Colors.white,
              fontWeight: FontWeight.w900,
            ),
          ),
        ],
      ),
    );
  }
}

class _GateTile extends StatelessWidget {
  const _GateTile({
    required this.label,
    required this.value,
    required this.active,
  });

  final String label;
  final String value;
  final bool active;

  @override
  Widget build(BuildContext context) {
    final color = active ? Colors.orangeAccent : Colors.greenAccent;
    return Container(
      width: 220,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withValues(alpha: 0.26)),
      ),
      child: Row(
        children: [
          Icon(Icons.shield_outlined, color: color, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: const TextStyle(
                    color: Colors.white70,
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  value,
                  style: TextStyle(color: color, fontWeight: FontWeight.w900),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ModuleTile extends StatelessWidget {
  const _ModuleTile({
    required this.label,
    required this.enabled,
    required this.detail,
  });

  final String label;
  final bool enabled;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final color = enabled ? Colors.lightBlueAccent : Colors.white54;
    return Container(
      width: 210,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 5),
          Text(
            enabled ? 'ON' : 'OFF',
            style: TextStyle(color: color, fontWeight: FontWeight.w900),
          ),
          const SizedBox(height: 3),
          Text(
            detail,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white60, fontSize: 12),
          ),
        ],
      ),
    );
  }
}

class _Line extends StatelessWidget {
  const _Line({
    required this.label,
    required this.value,
    this.valueColor,
  });

  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 140,
          child: Text(
            label,
            style: const TextStyle(color: Colors.white60),
          ),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: valueColor ?? Colors.white70,
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
      ],
    );
  }
}

bool _requiresAcknowledgement(String mode) =>
    mode == 'dry_run_auto' || mode == 'phase1_live_ready';
