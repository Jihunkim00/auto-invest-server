import 'package:flutter/material.dart';

import '../../core/i18n/app_strings.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/section_card.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';

/// User-facing Home surface. Advanced diagnostics and raw runtime controls stay
/// behind Admin; this screen only reports the effective operation state.
class HomeScreen extends StatelessWidget {
  const HomeScreen({
    super.key,
    required this.controller,
    this.onOpenAdmin,
    this.onOpenAutomationProfile,
  });

  final DashboardController controller;
  final VoidCallback? onOpenAdmin;
  final VoidCallback? onOpenAutomationProfile;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.load,
          child: ListView(
            key: const ValueKey('home-simple-scroll-view'),
            padding: const EdgeInsets.all(AppTheme.pagePadding),
            children: [
              _HomeHeader(controller: controller, onOpenAdmin: onOpenAdmin),
              const SizedBox(height: 16),
              _AccountConnectionCard(controller: controller),
              const SizedBox(height: 12),
              _OperationModeCard(controller: controller),
              const SizedBox(height: 12),
              _AutomationProfileCard(
                controller: controller,
                onOpen: onOpenAutomationProfile,
              ),
              const SizedBox(height: 12),
              _PortfolioCard(controller: controller),
              const SizedBox(height: 12),
              _PositionsCard(controller: controller),
              const SizedBox(height: 12),
              _DecisionCard(controller: controller),
              if (controller.error != null) ...[
                const SizedBox(height: 12),
                _InlineNotice(
                  message: controller.error!,
                  color: AppTheme.warning,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _HomeHeader extends StatelessWidget {
  const _HomeHeader({required this.controller, required this.onOpenAdmin});

  final DashboardController controller;
  final VoidCallback? onOpenAdmin;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    return LayoutBuilder(
      builder: (context, constraints) {
        final controls = Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            GlobalBrokerSelector(controller: controller),
            const SizedBox(width: 8),
            IconButton(
              key: const ValueKey('home-open-admin'),
              tooltip: strings.adminTooltip,
              onPressed: onOpenAdmin,
              icon: const Icon(Icons.admin_panel_settings_outlined),
            ),
          ],
        );
        final title = Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              strings.home,
              style: Theme.of(context).textTheme.headlineMedium,
            ),
            const SizedBox(height: 4),
            Text(
              controller.isKisSelected
                  ? strings.homeKisSubtitle
                  : strings.homeAlpacaSubtitle,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Colors.white70,
                  ),
            ),
          ],
        );
        if (constraints.maxWidth < 650) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [title, const SizedBox(height: 10), controls],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [Expanded(child: title), controls],
        );
      },
    );
  }
}

class _AccountConnectionCard extends StatelessWidget {
  const _AccountConnectionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    final broker = controller.selectedProvider == SelectedProvider.kis
        ? strings.kisBroker
        : strings.alpacaBroker;
    final failed = controller.portfolioLoadError != null ||
        (!controller.portfolioLoaded &&
            controller.selectedPortfolioUnavailable);
    final loading = !failed && !controller.portfolioLoaded;
    final color = failed
        ? AppTheme.warning
        : loading
            ? AppTheme.primaryAccent
            : AppTheme.positive;
    final label = failed
        ? strings.connectionError
        : loading
            ? strings.connectionLoading(broker)
            : strings.connectionSuccess(broker);
    final icon = failed
        ? Icons.error_outline
        : loading
            ? Icons.sync
            : Icons.check_circle_outline;

    return SectionCard(
      key: const ValueKey('home-account-connection-status'),
      padding: const EdgeInsets.all(14),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, color: color, size: 22),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  label,
                  style: TextStyle(color: color, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 3),
                Text(
                  failed
                      ? strings.connectionError
                      : strings.isKorean
                          ? '브로커 계좌·자산 데이터를 성공적으로 조회해야 연결됨으로 표시됩니다.'
                          : 'Connected means broker account and portfolio data was fetched successfully.',
                  style: const TextStyle(color: Colors.white60, height: 1.35),
                ),
                if (!loading && controller.portfolioLoadedAt != null) ...[
                  const SizedBox(height: 3),
                  Text(
                    strings
                        .updatedAt(_timeLabel(controller.portfolioLoadedAt!)),
                    style: const TextStyle(color: Colors.white54, fontSize: 12),
                  ),
                ],
              ],
            ),
          ),
          if (failed)
            Padding(
              padding: const EdgeInsets.only(left: 8),
              child: OutlinedButton(
                key: const ValueKey('home-account-connection-retry'),
                onPressed: controller.loading ? null : controller.load,
                child: Text(strings.retry),
              ),
            ),
        ],
      ),
    );
  }
}

class _AutomationProfileCard extends StatelessWidget {
  const _AutomationProfileCard({required this.controller, this.onOpen});

  final DashboardController controller;
  final VoidCallback? onOpen;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    return SectionCard(
      key: const ValueKey('home-automation-profile-card'),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final narrow = constraints.maxWidth < 520;
          final content = Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.tune_outlined, color: AppTheme.primaryAccent),
              const SizedBox(width: 10),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(strings.automationProfile,
                        style: Theme.of(context).textTheme.titleMedium),
                    const SizedBox(height: 4),
                    Text(strings.automationProfileDescription,
                        style: const TextStyle(
                            color: Colors.white70, height: 1.35)),
                  ],
                ),
              ),
              if (!narrow) ...[
                const SizedBox(width: 12),
                OutlinedButton(
                  key: const ValueKey('home-open-automation-profile'),
                  onPressed: onOpen,
                  child: Text(strings.configure),
                ),
              ],
            ],
          );
          if (!narrow) return content;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              content,
              const SizedBox(height: 12),
              OutlinedButton(
                key: const ValueKey('home-open-automation-profile'),
                onPressed: onOpen,
                child: Text(strings.configure),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _OperationModeCard extends StatelessWidget {
  const _OperationModeCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    final mode = controller.settings.currentOperationMode;
    final color = _operationModeColor(mode);
    final loading = controller.kisAutomationSettingsLoading;
    final detail = _operationModeDetail(strings, mode);

    return SectionCard(
      key: const ValueKey('home-operation-mode-card'),
      padding: EdgeInsets.zero,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          key: const ValueKey('home-operation-mode-selector'),
          borderRadius: BorderRadius.circular(16),
          onTap: loading ? null : () => _selectOperationMode(context),
          child: Padding(
            padding: const EdgeInsets.all(14),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Icons.shield_outlined, color: color),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(strings.operationMode,
                          style: Theme.of(context).textTheme.titleMedium),
                      const SizedBox(height: 4),
                      Text(
                        _operationModeLabel(strings, mode),
                        style: TextStyle(
                          color: color,
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(detail,
                          style: const TextStyle(
                              color: Colors.white70, height: 1.35)),
                      const SizedBox(height: 12),
                      Text(
                        strings.isKorean ? '현재 실행 가능 상태' : 'Execution status',
                        style: const TextStyle(
                          color: Colors.white54,
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 3),
                      Text(
                        _executionStatusLabel(strings, controller),
                        style: TextStyle(
                          color: _executionStatusColor(controller),
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          _ModeStatePill(
                            label: strings.isKorean ? 'Dry-run' : 'Dry-run',
                            enabled: controller.settings.dryRun,
                          ),
                          _ModeStatePill(
                            label:
                                strings.isKorean ? 'KIS 스케줄러' : 'KIS scheduler',
                            enabled: controller.settings.kisSchedulerEnabled,
                          ),
                          _ModeStatePill(
                            label: strings.isKorean ? '실주문 허용' : 'Real orders',
                            enabled:
                                controller.settings.kisSchedulerAllowRealOrders,
                            alert:
                                controller.settings.kisSchedulerAllowRealOrders,
                          ),
                          _ModeStatePill(
                            label: strings.isKorean ? '브로커 동기화' : 'Broker sync',
                            enabled: controller
                                    .automationModeStatus?.brokerSyncHealth ==
                                'healthy',
                            alert: controller.automationModeStatus != null &&
                                controller.automationModeStatus!
                                        .brokerSyncHealth !=
                                    'healthy',
                          ),
                          _ModeStatePill(
                            label: strings.isKorean ? '킬 스위치' : 'Kill switch',
                            enabled: controller.settings.killSwitch,
                            alert: controller.settings.killSwitch,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                loading
                    ? const SizedBox(
                        width: 20,
                        height: 20,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.chevron_right, color: Colors.white54),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _selectOperationMode(BuildContext context) async {
    final selected = await showModalBottomSheet<String>(
      context: context,
      backgroundColor: AppTheme.surface,
      isScrollControlled: true,
      builder: (sheetContext) {
        var selectedMode = controller.settings.currentOperationMode;
        return StatefulBuilder(
          builder: (context, setState) => SafeArea(
            child: Padding(
              padding: const EdgeInsets.fromLTRB(20, 20, 20, 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    controller.strings.isKorean
                        ? '운영 모드 변경'
                        : 'Change operation mode',
                    style: Theme.of(context).textTheme.titleLarge,
                  ),
                  const SizedBox(height: 12),
                  RadioGroup<String>(
                    groupValue: selectedMode,
                    onChanged: (value) {
                      if (controller.kisAutomationSettingsLoading) return;
                      setState(() => selectedMode = value!);
                    },
                    child: Column(
                      children: [
                        for (final option in _homeOperationModeOptions)
                          RadioListTile<String>(
                            key:
                                ValueKey('home-operation-mode-${option.value}'),
                            value: option.value,
                            activeColor: _operationModeColor(option.value),
                            contentPadding: EdgeInsets.zero,
                            title: Text(
                              _operationModeLabel(
                                controller.strings,
                                option.value,
                              ),
                            ),
                            subtitle: Text(
                              _operationModeDetail(
                                controller.strings,
                                option.value,
                              ),
                              style: const TextStyle(color: Colors.white60),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          key: const ValueKey('home-operation-mode-cancel'),
                          onPressed: () => Navigator.of(sheetContext).pop(),
                          child: Text(controller.strings.cancel),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: FilledButton(
                          key: const ValueKey('home-operation-mode-apply'),
                          onPressed: controller.kisAutomationSettingsLoading
                              ? null
                              : () =>
                                  Navigator.of(sheetContext).pop(selectedMode),
                          child: Text(
                              controller.strings.isKorean ? '적용' : 'Apply'),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
    if (!context.mounted ||
        selected == null ||
        selected == controller.settings.currentOperationMode) {
      return;
    }

    var confirmed = selected != 'full_live_test_mode';
    if (!confirmed) {
      confirmed = await _confirmLiveMode(context);
    }
    if (!context.mounted || !confirmed) return;

    final result = await controller.applyOperationModePreset(
      selected,
      confirmDangerous: selected == 'full_live_test_mode',
    );
    if (!context.mounted) return;
    // Home is normally hosted by the application Scaffold. Keep widget-level
    // usage safe as well (for previews and isolated tests).
    if (Scaffold.maybeOf(context) != null) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(result.message),
          backgroundColor: result.success ? AppTheme.positive : AppTheme.danger,
        ),
      );
    }
  }

  Future<bool> _confirmLiveMode(BuildContext context) async {
    final korean = controller.strings.isKorean;
    return await showDialog<bool>(
          context: context,
          builder: (dialogContext) => AlertDialog(
            title: Text(korean ? '실거래 모드로 변경' : 'Change to live mode'),
            content: Text(
              korean
                  ? '한국투자증권 실제 계좌 주문이 가능한 자동매매 모드입니다.\n\n자동매매 조건과 리스크 기준을 모두 충족한 경우 실제 주문이 제출될 수 있습니다.'
                  : 'This automation mode can place orders for a real KIS account. Real orders are submitted only after every risk and safety gate passes.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.of(dialogContext).pop(false),
                child: Text(controller.strings.cancel),
              ),
              FilledButton(
                key: const ValueKey('home-operation-mode-live-confirm'),
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: Text(korean ? '실거래 모드로 변경' : 'Change to live mode'),
              ),
            ],
          ),
        ) ??
        false;
  }
}

class _HomeOperationModeOption {
  const _HomeOperationModeOption(this.value);

  final String value;
}

const _homeOperationModeOptions = [
  _HomeOperationModeOption('safe_mode'),
  _HomeOperationModeOption('dry_run_simulation'),
  _HomeOperationModeOption('full_live_test_mode'),
];

class _ModeStatePill extends StatelessWidget {
  const _ModeStatePill({
    required this.label,
    required this.enabled,
    this.alert = false,
  });

  final String label;
  final bool enabled;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    final color = alert
        ? AppTheme.danger
        : enabled
            ? AppTheme.positive
            : Colors.white54;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        '$label ${enabled ? 'ON' : 'OFF'}',
        style:
            TextStyle(color: color, fontSize: 11, fontWeight: FontWeight.w700),
      ),
    );
  }
}

String _operationModeLabel(AppStrings strings, String mode) {
  final korean = strings.isKorean;
  return switch (mode.trim()) {
    'safe_mode' => korean ? '테스트' : 'Test',
    'dry_run_simulation' => korean ? '모의투자' : 'Paper',
    'full_live_test_mode' => korean ? '실거래' : 'Live',
    'manual_live_trading' => korean ? '수동 실거래' : 'Manual live trading',
    'kis_sell_only_automation' => korean ? '매도 전용 실거래' : 'Sell-only live',
    _ => korean ? '사용자 설정' : 'Custom',
  };
}

String _operationModeDetail(AppStrings strings, String mode) {
  final korean = strings.isKorean;
  return switch (mode.trim()) {
    'safe_mode' => korean
        ? '주문을 제출하지 않는 안전한 운영 모드'
        : 'Safe operation mode that never submits an order.',
    'dry_run_simulation' => korean
        ? '실제 주문 없이 자동 분석과 시뮬레이션을 실행합니다.'
        : 'Runs automated analysis and simulation without real orders.',
    'full_live_test_mode' => korean
        ? '모든 안전 게이트 통과 후 KIS 실제 주문이 가능합니다.'
        : 'KIS real orders remain possible only after all safety gates pass.',
    _ => korean
        ? '서버 설정과 안전 게이트가 현재 실행을 결정합니다.'
        : 'Server settings and safety gates determine current execution.',
  };
}

Color _operationModeColor(String mode) => switch (mode.trim()) {
      'full_live_test_mode' => AppTheme.danger,
      'dry_run_simulation' => AppTheme.primaryAccent,
      'safe_mode' => AppTheme.positive,
      _ => AppTheme.warning,
    };

String _executionStatusLabel(
    AppStrings strings, DashboardController controller) {
  final korean = strings.isKorean;
  final mode = controller.settings.currentOperationMode;
  if (controller.settings.killSwitch) return korean ? '실거래 차단' : 'Live blocked';
  if (mode == 'full_live_test_mode') {
    return controller.automationModeStatus?.canSubmitLiveOrder == true
        ? (korean ? '실거래 준비됨' : 'Live ready')
        : (korean ? '실거래 준비 점검 필요' : 'Live readiness required');
  }
  if (mode == 'dry_run_simulation') {
    return korean ? '모의투자 실행 가능' : 'Paper simulation ready';
  }
  return korean ? '테스트/안전 실행' : 'Test/safe execution';
}

Color _executionStatusColor(DashboardController controller) {
  if (controller.settings.killSwitch) return AppTheme.danger;
  if (controller.settings.currentOperationMode == 'full_live_test_mode') {
    return controller.automationModeStatus?.canSubmitLiveOrder == true
        ? AppTheme.positive
        : AppTheme.warning;
  }
  return AppTheme.primaryAccent;
}

class _PortfolioCard extends StatelessWidget {
  const _PortfolioCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    final summary = controller.selectedPortfolioSummary;
    final unavailable = controller.selectedPortfolioUnavailable ||
        summary.hasUnavailableKisData;
    if (!controller.portfolioLoaded) {
      return SectionCard(
        key: const ValueKey('home-portfolio-card'),
        child: Row(
          children: [
            const Icon(
              Icons.hourglass_empty_outlined,
              size: 20,
              color: AppTheme.primaryAccent,
            ),
            const SizedBox(width: 10),
            Expanded(
                child: Text(strings.connectionLoading(
                    controller.selectedProvider == SelectedProvider.kis
                        ? strings.kisBroker
                        : strings.alpacaBroker))),
          ],
        ),
      );
    }
    final total =
        summary.totalMarketValue + (summary.cashKnown ? summary.cash : 0);
    return SectionCard(
      key: const ValueKey('home-portfolio-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(strings.portfolio,
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 10),
          if (unavailable)
            _InlineNotice(
              message: strings.unavailablePortfolio,
              color: AppTheme.warning,
            ),
          Wrap(
            spacing: 24,
            runSpacing: 14,
            children: [
              _Metric(strings.value, _money(summary.currency, total)),
              _Metric(
                  strings.cash,
                  summary.cashKnown
                      ? _money(summary.currency, summary.cash)
                      : strings.unknownValue),
              _Metric(strings.pnl,
                  _signedMoney(summary.currency, summary.totalUnrealizedPl)),
            ],
          ),
        ],
      ),
    );
  }
}

class _PositionsCard extends StatelessWidget {
  const _PositionsCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    final positions = controller.selectedPortfolioSummary.positions
        .take(3)
        .toList(growable: false);
    return SectionCard(
      key: const ValueKey('home-positions-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(strings.currentPositions,
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          if (!controller.portfolioLoaded)
            Text(
                strings.connectionLoading(
                    controller.selectedProvider == SelectedProvider.kis
                        ? strings.kisBroker
                        : strings.alpacaBroker),
                style: const TextStyle(color: Colors.white70))
          else if (positions.isEmpty)
            Text(strings.noHeldPositions,
                style: const TextStyle(color: Colors.white70))
          else
            for (final position in positions)
              Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: Text(
                        position.name.isEmpty
                            ? position.symbol
                            : '${position.name} (${position.symbol})',
                        softWrap: true,
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text('${strings.qty} ${_number(position.qty)}',
                        style: const TextStyle(color: Colors.white70)),
                    const SizedBox(width: 10),
                    Flexible(
                      child: Text(
                        _signedMoney(
                            controller.selectedPortfolioSummary.currency,
                            position.unrealizedPl),
                        textAlign: TextAlign.right,
                        style: TextStyle(
                          color: position.unrealizedPl >= 0
                              ? AppTheme.positive
                              : AppTheme.danger,
                          fontWeight: FontWeight.w700,
                        ),
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

class _DecisionCard extends StatelessWidget {
  const _DecisionCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final strings = controller.strings;
    final run = controller.runResult;
    final action = strings.decisionLabel(run.action);
    final candidate = run.finalBestCandidate.trim().isEmpty
        ? strings.noCandidateYet
        : run.finalBestCandidate;
    final reason = run.triggerBlockReason.trim().isEmpty
        ? run.reason.trim().isEmpty
            ? strings.askAiForAnalysis
            : run.reason
        : run.triggerBlockReason;
    return SectionCard(
      key: const ValueKey('home-decision-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(strings.latestDecision,
              style: Theme.of(context).textTheme.titleMedium),
          const SizedBox(height: 8),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(action,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.w900)),
              const SizedBox(width: 10),
              Expanded(child: Text(candidate, softWrap: true)),
            ],
          ),
          const SizedBox(height: 4),
          Text(reason,
              style: const TextStyle(color: Colors.white70, height: 1.35)),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric(this.label, this.value);

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(color: Colors.white54)),
        const SizedBox(height: 3),
        Text(value, style: const TextStyle(fontWeight: FontWeight.w800)),
      ],
    );
  }
}

class _InlineNotice extends StatelessWidget {
  const _InlineNotice({required this.message, required this.color});

  final String message;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 18, color: color),
          const SizedBox(width: 8),
          Expanded(
              child:
                  Text(message, style: TextStyle(color: color, height: 1.35))),
        ],
      ),
    );
  }
}

String _money(String currency, double value) {
  final code = currency.trim().toUpperCase();
  if (code == 'KRW') return '₩${value.toStringAsFixed(0)}';
  return '${code == 'USD' || code.isEmpty ? '\$' : '$code '}${value.toStringAsFixed(2)}';
}

String _signedMoney(String currency, double value) {
  final sign = value > 0 ? '+' : '';
  return '$sign${_money(currency, value)}';
}

String _number(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}

String _timeLabel(DateTime value) {
  final local = value.toLocal();
  return '${local.hour.toString().padLeft(2, '0')}:${local.minute.toString().padLeft(2, '0')}';
}
