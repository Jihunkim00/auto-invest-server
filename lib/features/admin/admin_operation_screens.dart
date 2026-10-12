import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../models/kis_single_symbol_trading_result.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/manual_order_screen.dart';
import '../dashboard/widgets/broker_context_controls.dart';
import '../dashboard/widgets/order_ticket_section.dart';
import '../dashboard/widgets/portfolio_snapshot_section.dart';

class AdminSingleSymbolAnalysisScreen extends StatefulWidget {
  const AdminSingleSymbolAnalysisScreen({super.key, required this.controller});
  final DashboardController controller;

  @override
  State<AdminSingleSymbolAnalysisScreen> createState() =>
      _AdminSingleSymbolAnalysisScreenState();
}

class _AdminSingleSymbolAnalysisScreenState
    extends State<AdminSingleSymbolAnalysisScreen> {
  final _symbol = TextEditingController();
  bool _loading = false;
  String? _error;
  KisSingleSymbolTradingResult? _result;

  @override
  void dispose() {
    _symbol.dispose();
    super.dispose();
  }

  Future<void> _analyze() async {
    final symbol = _symbol.text.trim();
    if (_loading ||
        !RegExp(r'^\d{6}$').hasMatch(symbol) ||
        !widget.controller.isKisSelected ||
        widget.controller.regularUserHomeBootstrapStarted) {
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
      _result = null;
    });
    try {
      final result =
          await widget.controller.apiClient.runKisSingleSymbolAnalyzeBuy(
        symbol: symbol,
        gateLevel: widget.controller.selectedGateLevel,
        requestedAction: 'analyze_only',
        confirmLive: false,
        dryRun: true,
        sourceContext: const {'source': 'admin_single_symbol_analysis'},
      );
      if (!mounted) return;
      setState(() => _result = result);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
        animation: widget.controller,
        builder: (context, _) {
          if (widget.controller.regularUserHomeBootstrapStarted) {
            return const Center(child: Text('관리자 권한이 필요합니다.'));
          }
          final isKis = widget.controller.isKisSelected;
          final valid = RegExp(r'^\d{6}$').hasMatch(_symbol.text.trim());
          return ListView(padding: const EdgeInsets.all(16), children: [
            AdminBrokerHeader(controller: widget.controller),
            const SizedBox(height: 12),
            const Text('분석 전용 · 실주문 없음',
                style: TextStyle(
                    color: Colors.lightBlueAccent,
                    fontWeight: FontWeight.w700)),
            const SizedBox(height: 8),
            const Text('현재가, 점수와 HOLD 사유를 확인합니다. 매수·매도는 관리자 메뉴에서 별도로 선택하세요.'),
            const SizedBox(height: 16),
            if (!isKis) const Text('단일 종목 분석은 KIS를 선택한 후 이용할 수 있습니다.'),
            TextField(
              key: const ValueKey('admin-analysis-symbol'),
              controller: _symbol,
              enabled: isKis && !_loading,
              keyboardType: TextInputType.number,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(6)
              ],
              decoration: InputDecoration(
                  labelText: 'KIS 종목코드 (6자리)',
                  hintText: '005930',
                  errorText: _symbol.text.isNotEmpty && !valid
                      ? '종목코드 6자리를 입력하세요.'
                      : null),
              onChanged: (_) => setState(() {
                _result = null;
                _error = null;
              }),
            ),
            const SizedBox(height: 12),
            FilledButton.icon(
              key: const ValueKey('admin-analysis-run'),
              onPressed: isKis && valid && !_loading ? _analyze : null,
              icon: _loading
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.analytics_outlined),
              label: Text(_loading ? '분석 중...' : '단일 종목 분석'),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!, style: const TextStyle(color: Colors.redAccent))
            ],
            if (isKis && _result != null) ...[
              const SizedBox(height: 16),
              _AnalysisHighlights(result: _result!),
              KisSingleSymbolAnalysisResult(
                  result: _result!, selectedSymbol: _symbol.text.trim()),
            ],
          ]);
        });
  }
}

enum AdminOperation { manualOrder, account, orders }

class AdminOperationScreen extends StatelessWidget {
  const AdminOperationScreen(
      {super.key, required this.controller, required this.operation});
  final DashboardController controller;
  final AdminOperation operation;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
        animation: controller,
        builder: (context, _) {
          if (controller.regularUserHomeBootstrapStarted) {
            return const Center(child: Text('관리자 권한이 필요합니다.'));
          }
          final isSell = controller.orderTicketSide == 'sell';
          return ListView(padding: const EdgeInsets.all(16), children: [
            AdminBrokerHeader(controller: controller),
            const SizedBox(height: 12),
            if (operation == AdminOperation.account) ...[
              const Text('조회 전용 · 선택한 브로커의 계좌와 보유 종목'),
              const SizedBox(height: 12),
              _PortfolioContent(controller: controller),
            ] else if (!controller.isKisSelected)
              const Text('이 기능은 KIS를 선택한 후 이용할 수 있습니다.')
            else if (operation == AdminOperation.manualOrder) ...[
              Text(isSell ? '단일 종목 매도 · KIS 실거래' : '단일 종목 매수 · KIS 실거래',
                  style: TextStyle(
                      color: isSell ? Colors.orangeAccent : Colors.redAccent,
                      fontWeight: FontWeight.w700)),
              const SizedBox(height: 8),
              const Text('사전 검증 → 실거래 확인 체크 → 최종 확인을 완료해야 주문이 제출됩니다.'),
              const SizedBox(height: 12),
              if (isSell) _ManualSellPreparationButton(controller: controller),
              OrderTicketSection(controller: controller),
              if (isSell)
                Card(
                    child: ExpansionTile(
                  key: const ValueKey('admin-sell-positions'),
                  title: const Text('보유 종목 조회 / 매도 준비'),
                  subtitle: const Text('보유 수량을 조회하고 매도 티켓을 준비합니다.'),
                  children: [
                    _PortfolioContent(
                        controller: controller, managementMode: true)
                  ],
                )),
            ] else ...[
              const Text('주문 내역 / 체결 조회 · 신규 주문 제출 없음'),
              const SizedBox(height: 12),
              OutlinedButton.icon(
                key: const ValueKey('admin-orders-refresh'),
                onPressed: controller.kisOrdersLoading
                    ? null
                    : () => controller.refreshKisOrderMonitoring(),
                icon: const Icon(Icons.refresh),
                label: const Text('주문 내역 새로고침'),
              ),
              if (controller.kisOrdersLoading) const LinearProgressIndicator(),
              if (controller.kisManualOrderError != null)
                Text(controller.kisManualOrderError!,
                    style: const TextStyle(color: Colors.redAccent)),
              KisOrderStatusPanel(
                  controller: controller,
                  latest: controller.latestKisManualOrder,
                  selected: controller.selectedKisOrder,
                  orders: controller.kisOrders),
            ],
          ]);
        });
  }
}

class _PortfolioContent extends StatelessWidget {
  const _PortfolioContent(
      {required this.controller, this.managementMode = false});
  final DashboardController controller;
  final bool managementMode;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      OutlinedButton.icon(
        onPressed: controller.portfolioManagementLoading
            ? null
            : () => controller.refreshPortfolioManagement(),
        icon: const Icon(Icons.refresh),
        label: const Text('계좌 / 보유 종목 새로고침'),
      ),
      if (controller.portfolioManagementLoading)
        const LinearProgressIndicator(),
      if (controller.portfolioManagementError != null)
        Text(controller.portfolioManagementError!,
            style: const TextStyle(color: Colors.redAccent)),
      PortfolioSnapshotSection(
          controller: controller,
          koreanLabels: true,
          managementMode: managementMode,
          // The prepared sell ticket is already displayed on this page.
          onOpenManualOrder: managementMode ? () {} : null),
    ]);
  }
}

class AdminBrokerHeader extends StatelessWidget {
  const AdminBrokerHeader({super.key, required this.controller});
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Wrap(
        spacing: 12,
        runSpacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          BrokerContextBadge(controller: controller),
          GlobalBrokerSelector(controller: controller),
        ]);
  }
}

class _ManualSellPreparationButton extends StatefulWidget {
  const _ManualSellPreparationButton({required this.controller});
  final DashboardController controller;
  @override
  State<_ManualSellPreparationButton> createState() =>
      _ManualSellPreparationButtonState();
}

class _ManualSellPreparationButtonState
    extends State<_ManualSellPreparationButton> {
  bool _loading = false;
  String? _message;
  bool _success = false;

  Future<void> _prepare() async {
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      final result = await widget.controller
          .prepareKisManualSellFromSymbol(widget.controller.orderTicketSymbol);
      if (!mounted) return;
      setState(() {
        _message = result.message;
        _success = result.success;
      });
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
      OutlinedButton.icon(
        key: const ValueKey('admin-prepare-sell'),
        onPressed: _loading ||
                widget.controller.orderValidationLoading ||
                widget.controller.kisManualSubmitLoading ||
                !RegExp(r'^\d{6}$')
                    .hasMatch(widget.controller.orderTicketSymbol)
            ? null
            : _prepare,
        icon: _loading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.inventory_2_outlined),
        label: const Text('입력한 종목의 보유 수량 조회 / 매도 준비'),
      ),
      if (_message != null)
        Text(_message!,
            style: TextStyle(
                color: _success ? Colors.lightBlueAccent : Colors.redAccent)),
      const SizedBox(height: 12),
    ]);
  }
}

class _AnalysisHighlights extends StatelessWidget {
  const _AnalysisHighlights({required this.result});
  final KisSingleSymbolTradingResult result;

  @override
  Widget build(BuildContext context) {
    final raw = result.rawPayload;
    final details =
        raw['quant_details'] is Map ? raw['quant_details'] as Map : const {};
    final gpt =
        raw['gpt_context'] is Map ? raw['gpt_context'] as Map : const {};
    return Card(
      key: const ValueKey('admin-analysis-summary'),
      child: Padding(
          padding: const EdgeInsets.all(12),
          child: Wrap(spacing: 16, runSpacing: 8, children: [
            Text('현재가: ${result.currentPrice ?? '미제공'}'),
            Text('퀀트 점수: ${result.quantBuyScore ?? '미제공'}'),
            Text(
                'A 점수: ${raw['quant_a_score'] ?? details['quant_a_score'] ?? '미제공'}'),
            Text(
                'C 점수: ${raw['quant_c_score'] ?? details['quant_c_score'] ?? '미제공'}'),
            Text(
                '데이터 품질: ${result.indicatorStatus ?? raw['data_quality_status'] ?? '미제공'}'),
            Text(
                'GPT 상태: ${raw['gpt_analysis_status'] ?? gpt['status'] ?? '미제공'}'),
            Text(
                'GPT 매수 점수: ${result.gptBuyScore ?? result.aiBuyScore ?? '미제공'}'),
          ])),
    );
  }
}
