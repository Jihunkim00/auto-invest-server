import 'package:flutter/material.dart';

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
    final mode = controller.operationModeStatus;
    final blocked = mode.isBlocked;
    final color = blocked ? AppTheme.warning : AppTheme.primaryAccent;
    final detail = mode.blockingReasons.isNotEmpty
        ? strings.statusLabel(mode.blockingReasons.first.code)
        : mode.warnings.isNotEmpty
            ? strings.statusLabel(mode.warnings.first.code)
            : (strings.isKorean
                ? '현재 운영 상태와 서버 안전 게이트를 따릅니다.'
                : 'The current operation state and server safety gates apply.');

    return SectionCard(
      key: const ValueKey('home-operation-mode-card'),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(blocked ? Icons.warning_amber_outlined : Icons.shield_outlined,
              color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(strings.operationMode,
                    style: Theme.of(context).textTheme.titleMedium),
                const SizedBox(height: 4),
                Text(
                  strings.operationModeLabel(mode.effectiveMode),
                  style: TextStyle(
                      color: color, fontSize: 18, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(detail, style: const TextStyle(color: Colors.white70)),
              ],
            ),
          ),
        ],
      ),
    );
  }
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
