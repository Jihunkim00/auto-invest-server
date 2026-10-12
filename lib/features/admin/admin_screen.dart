import 'package:flutter/material.dart';

import '../analysis/analysis_screen.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/manual_order_screen.dart';
import '../dashboard/test_lab_screen.dart';
import '../dashboard/watchlist_screen.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import '../logs/logs_screen.dart';
import '../settings/settings_screen.dart';
import 'admin_operation_screens.dart';
import 'admin_user_management_panel.dart';

class AdminScreen extends StatelessWidget {
  const AdminScreen({super.key, required this.controller, this.onLogout});
  final DashboardController controller;
  final Future<void> Function()? onLogout;

  void _open(BuildContext context, String title, Widget screen) {
    if (controller.regularUserHomeBootstrapStarted) return;
    Navigator.of(context).push(MaterialPageRoute<void>(
        builder: (_) =>
            Scaffold(appBar: AppBar(title: Text(title)), body: screen)));
  }

  void _openOrder(BuildContext context, String side) {
    if (controller.regularUserHomeBootstrapStarted) return;
    controller.setOrderTicketSide(side);
    controller.setKisLiveConfirmation(false);
    controller.setKisGuardedRunConfirmation(false);
    _open(
        context,
        side == 'sell' ? '단일 종목 매도' : '단일 종목 매수',
        AdminOperationScreen(
            controller: controller, operation: AdminOperation.manualOrder));
  }

  Widget _item(BuildContext context, String key, IconData icon, String title,
      Widget screen,
      {String? subtitle}) {
    return _AdminItem(
        key: ValueKey(key),
        icon: icon,
        title: title,
        subtitle: subtitle,
        onTap: () => _open(context, title, screen));
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
        animation: controller,
        builder: (context, _) => Scaffold(
              appBar: AppBar(title: const Text('관리자 도구')),
              body: controller.regularUserHomeBootstrapStarted
                  ? const Center(child: Text('관리자 권한이 필요합니다.'))
                  : ListView(padding: const EdgeInsets.all(16), children: [
                      const Text('관리자 전용 · 분석과 조회는 실주문을 제출하지 않습니다.',
                          style: TextStyle(color: Colors.white70)),
                      const SizedBox(height: 12),
                      GlobalBrokerSelector(controller: controller),
                      const SizedBox(height: 12),
                      _AdminGroup(title: '빠른 작업', items: [
                        _item(
                            context,
                            'admin-open-analysis',
                            Icons.analytics_outlined,
                            '단일 종목 분석',
                            AdminSingleSymbolAnalysisScreen(
                                controller: controller),
                            subtitle: '분석 전용 · 실주문 없음'),
                        _AdminItem(
                            key: const ValueKey('admin-open-manual-trading'),
                            icon: Icons.add_shopping_cart,
                            title: '단일 종목 매수',
                            subtitle: 'KIS 실거래 · 검증과 최종 확인 필요',
                            onTap: () => _openOrder(context, 'buy')),
                        _AdminItem(
                            key: const ValueKey('admin-open-manual-sell'),
                            icon: Icons.sell_outlined,
                            title: '단일 종목 매도',
                            subtitle: 'KIS 실거래 · 보유 수량 검증과 최종 확인 필요',
                            onTap: () => _openOrder(context, 'sell')),
                      ]),
                      _AdminGroup(title: '조회 및 관리', items: [
                        _item(
                            context,
                            'admin-open-portfolio',
                            Icons.account_balance_wallet_outlined,
                            '보유 종목 / 계좌 조회',
                            AdminOperationScreen(
                                controller: controller,
                                operation: AdminOperation.account),
                            subtitle: '조회 전용 · 선택한 브로커의 잔고와 평가손익'),
                        _item(
                            context,
                            'admin-open-orders',
                            Icons.receipt_long_outlined,
                            '주문 내역 / 체결 조회',
                            AdminOperationScreen(
                                controller: controller,
                                operation: AdminOperation.orders),
                            subtitle: 'KIS 주문 상태 · 주문번호 · 동기화'),
                        _item(
                            context,
                            'admin-open-logs',
                            Icons.monitor_heart_outlined,
                            '운영 로그 / 진단',
                            LogsScreen(controller: controller),
                            subtitle:
                                'BUY / SELL / HOLD · 차단 사유 · scheduler 상태'),
                        _item(
                            context,
                            'admin-open-watchlist',
                            Icons.manage_search,
                            'Watchlist 분석',
                            WatchlistScreen(
                                controller: controller,
                                onOpenManualOrder: () => _open(context, '수동 주문',
                                    TradingScreen(controller: controller)))),
                        _item(
                            context,
                            'admin-open-settings',
                            Icons.settings_outlined,
                            '위험관리 / 운영 설정',
                            SettingsScreen(
                                controller: controller, onLogout: onLogout)),
                        _item(
                            context,
                            'admin-open-accounts',
                            Icons.manage_accounts_outlined,
                            '관리자 계정 관리',
                            ListView(
                                padding: const EdgeInsets.all(16),
                                children: [
                                  AdminUserManagementPanel(
                                      apiClient: controller.apiClient),
                                ])),
                      ]),
                      Card(
                          child: ExpansionTile(
                        key: const ValueKey('admin-advanced-tools'),
                        title: const Text('고급 도구 / 진단'),
                        leading: const Icon(Icons.build_outlined),
                        children: [
                          _item(
                              context,
                              'admin-open-test4',
                              Icons.tune,
                              'KIS 자동매매 운영 상태',
                              TestLabScreen(controller: controller),
                              subtitle: '기존 테스트 도구와 scheduler 운영 화면'),
                          _item(
                              context,
                              'admin-open-decision-review',
                              Icons.rule_outlined,
                              '후보 분석 상세',
                              AnalysisScreen(
                                  controller: controller,
                                  onOpenManualOrder: () => _open(
                                      context,
                                      '수동 주문',
                                      TradingScreen(controller: controller)),
                                  onOpenDashboard: () =>
                                      Navigator.of(context).pop())),
                        ],
                      )),
                    ]),
            ));
  }
}

class _AdminGroup extends StatelessWidget {
  const _AdminGroup({required this.title, required this.items});
  final String title;
  final List<Widget> items;

  @override
  Widget build(BuildContext context) {
    return Card(
        margin: const EdgeInsets.only(bottom: 14),
        child: Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 8),
          child:
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(title,
                style: const TextStyle(
                    color: Colors.lightBlueAccent,
                    fontWeight: FontWeight.w800)),
            const SizedBox(height: 6),
            ...items,
          ]),
        ));
  }
}

class _AdminItem extends StatelessWidget {
  const _AdminItem(
      {super.key,
      required this.icon,
      required this.title,
      required this.onTap,
      this.subtitle});
  final IconData icon;
  final String title;
  final String? subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return ListTile(
        leading: Icon(icon),
        title: Text(title),
        subtitle: subtitle == null ? null : Text(subtitle!),
        trailing: const Icon(Icons.chevron_right),
        onTap: onTap);
  }
}
