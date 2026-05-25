import 'package:flutter/material.dart';

import '../../core/i18n/app_strings.dart';
import '../../core/widgets/language_toggle_chip.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import 'dashboard_controller.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key, required this.controller, this.onOpenManualOrder, this.onReviewPosition});
  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) {
        final l = controller.uiLanguage;
        return SafeArea(
          child: ListView(padding: const EdgeInsets.all(16), children: [
            Row(children: [
              LanguageToggleChip(isKorean: controller.isKoreanUi, onTap: controller.toggleUiLanguage),
              const Spacer(),
              GlobalBrokerSelector(controller: controller),
            ]),
            const SizedBox(height: 12),
            Text(AppStrings.t(AppTextKey.autoInvest, l), style: const TextStyle(fontSize: 28, fontWeight: FontWeight.w700)),
            Text(controller.selectedProvider == SelectedProvider.kis ? AppStrings.t(AppTextKey.kisSubtitle, l) : AppStrings.t(AppTextKey.alpacaSubtitle, l)),
            const SizedBox(height: 12),
            Wrap(spacing: 8, children: [Chip(label: Text(AppStrings.t(AppTextKey.autoBuyOff, l))), Chip(label: Text(AppStrings.t(AppTextKey.apiHealthy, l)))]),
            const SizedBox(height: 12),
            _card('Cash / Buying Power', '---'),
            _card(AppStrings.t(AppTextKey.todaySignal, l), AppStrings.t(AppTextKey.confidence, l)),
            _card(AppStrings.t(AppTextKey.preTradeCheck, l), 'max order / stop loss / scheduler'),
            _card(AppStrings.t(AppTextKey.recentEvents, l), 'latest 3 events'),
            FilledButton(onPressed: onOpenManualOrder, child: Text(AppStrings.t(AppTextKey.executeOrder, l))),
          ]),
        );
      },
    );
  }

  Widget _card(String title, String body) => Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [Text(title, style: const TextStyle(fontWeight: FontWeight.w700)), const SizedBox(height: 6), Text(body)])));
}
