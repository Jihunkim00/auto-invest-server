import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../../features/dashboard/dashboard_controller.dart';
import '../../models/user_broker_account_snapshot.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import '../dashboard/widgets/portfolio_snapshot_section.dart';

class UserAssetsScreen extends StatefulWidget {
  const UserAssetsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<UserAssetsScreen> createState() => _UserAssetsScreenState();
}

class _UserAssetsScreenState extends State<UserAssetsScreen> {
  SelectedProvider _selectedProvider = SelectedProvider.kis;

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final snapshot = controller.userBrokerAccountFor(_selectedProvider);
        final summary = controller.userPortfolioSummaryFor(_selectedProvider);
        final configured = controller.userBrokerCredentials.any(
          (credential) =>
              credential.configured &&
              credential.provider.trim().toLowerCase() ==
                  _providerCode(_selectedProvider),
        );
        return SafeArea(
          child: RefreshIndicator(
            onRefresh: controller.refreshUserBrokerAccounts,
            child: ListView(
              key: const ValueKey('user-assets-scroll-view'),
              physics: const AlwaysScrollableScrollPhysics(),
              padding: const EdgeInsets.all(16),
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '\uC790\uC0B0',
                        style: Theme.of(context).textTheme.headlineMedium,
                      ),
                    ),
                    GlobalBrokerSelector(
                      controller: controller,
                      selectedProvider: _selectedProvider,
                      onSelectionChanged: (provider) {
                        setState(() => _selectedProvider = provider);
                      },
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                _UserBrokerStatusCard(
                  controller: controller,
                  provider: _selectedProvider,
                  snapshot: snapshot,
                  configured: configured,
                ),
                const SizedBox(height: 12),
                if (summary != null)
                  PortfolioSnapshotSection(
                    controller: controller,
                    summaryOverride: summary,
                    providerOverride: _selectedProvider,
                    managementMode: false,
                    koreanLabels: true,
                  )
                else
                  _UserAccountEmptyState(
                    loading: controller
                        .userBrokerAccountLoadingFor(_selectedProvider),
                    configured: configured,
                    error:
                        controller.userBrokerAccountErrorFor(_selectedProvider),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  String _providerCode(SelectedProvider provider) {
    return provider == SelectedProvider.kis ? 'kis' : 'alpaca';
  }
}

class _UserBrokerStatusCard extends StatelessWidget {
  const _UserBrokerStatusCard({
    required this.controller,
    required this.provider,
    required this.snapshot,
    required this.configured,
  });

  final DashboardController controller;
  final SelectedProvider provider;
  final UserBrokerAccountSnapshot? snapshot;
  final bool configured;

  @override
  Widget build(BuildContext context) {
    final loading = controller.userBrokerAccountLoadingFor(provider);
    final error = controller.userBrokerAccountErrorFor(provider);
    final Color color;
    final IconData icon;
    final String title;
    if (loading) {
      color = Colors.amberAccent;
      icon = Icons.sync;
      title = '\uC5F0\uACB0 \uC0C1\uD0DC \uD655\uC778 \uC911\u2026';
    } else if (snapshot?.connected == true) {
      color = Colors.greenAccent;
      icon = Icons.check_circle_outline;
      title = '\uC5F0\uACB0\uB428';
    } else if (!configured || error == 'broker_credentials_not_configured') {
      color = Colors.white54;
      icon = Icons.link_off;
      title = '\uBBF8\uC124\uC815';
    } else {
      color = Colors.orangeAccent;
      icon = Icons.error_outline;
      title = '\uC5F0\uACB0 \uC624\uB958';
    }
    final broker = provider == SelectedProvider.kis
        ? 'KIS / \uAD6D\uB0B4'
        : 'Alpaca / \uBBF8\uAD6D';
    final environment = snapshot?.environment.trim().toLowerCase();
    final mode = environment == 'live' ? 'Live' : 'Paper';

    return SectionCard(
      key: const ValueKey('user-assets-account-status'),
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
                  title,
                  style: TextStyle(color: color, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  '$broker \u00B7 $mode',
                  style: const TextStyle(color: Colors.white70),
                ),
                if (snapshot?.connected == true)
                  const Padding(
                    padding: EdgeInsets.only(top: 4),
                    child: Text(
                      '\uACC4\uC88C \uC815\uBCF4\uB294 \uC870\uD68C \uC804\uC6A9\uC73C\uB85C \uD45C\uC2DC\uB429\uB2C8\uB2E4.',
                      style: TextStyle(color: Colors.white60),
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

class _UserAccountEmptyState extends StatelessWidget {
  const _UserAccountEmptyState({
    required this.loading,
    required this.configured,
    required this.error,
  });

  final bool loading;
  final bool configured;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final String message;
    if (loading) {
      message = '\uACC4\uC88C \uC815\uBCF4 \uD655\uC778 \uC911\u2026';
    } else if (!configured || error == 'broker_credentials_not_configured') {
      message =
          '\uACC4\uC88C \uC815\uBCF4\uAC00 \uC124\uC815\uB418\uC9C0 \uC54A\uC558\uC2B5\uB2C8\uB2E4.';
    } else {
      message =
          '\uACC4\uC88C \uC815\uBCF4 \uC870\uD68C\uC5D0 \uC2E4\uD328\uD588\uC2B5\uB2C8\uB2E4.';
    }
    return SectionCard(
      key: const ValueKey('user-assets-account-empty-state'),
      child: Row(
        children: [
          if (loading)
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          else
            const Icon(Icons.info_outline, color: Colors.white60),
          const SizedBox(width: 10),
          Expanded(child: Text(message)),
        ],
      ),
    );
  }
}
