import 'package:flutter/material.dart';

import '../../core/widgets/section_card.dart';
import '../admin/admin_screen.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import '../dashboard/widgets/portfolio_snapshot_section.dart';

class AssetsScreen extends StatelessWidget {
  const AssetsScreen({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => SafeArea(
        child: RefreshIndicator(
          onRefresh: controller.load,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Row(
                children: [
                  const Expanded(
                    child: Text('Assets',
                        style: TextStyle(
                            fontSize: 28, fontWeight: FontWeight.w700)),
                  ),
                  GlobalBrokerSelector(controller: controller),
                  IconButton(
                    key: const ValueKey('assets-open-admin'),
                    tooltip: 'Advanced / Admin',
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => AdminScreen(controller: controller),
                      ),
                    ),
                    icon: const Icon(Icons.admin_panel_settings_outlined),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              const Text(
                '계좌와 보유 종목을 확인합니다. 이 화면에서는 자동 매도나 주문을 실행하지 않습니다.',
                style: TextStyle(color: Colors.white70),
              ),
              const SizedBox(height: 14),
              SectionCard(
                key: const ValueKey('assets-summary-card'),
                child: Row(
                  children: [
                    const Icon(Icons.account_balance_wallet_outlined),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Text(
                        controller.selectedPortfolioSummary.currency +
                            ' · ' +
                            controller.selectedPortfolioSummary.positionsCount
                                .toString() +
                            '개 보유',
                        style: const TextStyle(fontWeight: FontWeight.w800),
                      ),
                    ),
                    Text(
                      _money(
                          controller.selectedPortfolioSummary.totalMarketValue,
                          controller.selectedPortfolioSummary.currency),
                      style: const TextStyle(
                          color: Colors.lightBlueAccent,
                          fontWeight: FontWeight.w900),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 12),
              PortfolioSnapshotSection(
                controller: controller,
                managementMode: false,
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _money(double value, String currency) {
    final amount = value.round().toString();
    final grouped = amount.replaceAllMapped(
      RegExp(r'(\d)(?=(\d{3})+(?!\d))'),
      (match) => match.group(1)! + ',',
    );
    return (currency == 'KRW' ? '₩' : '\$') + grouped;
  }
}
