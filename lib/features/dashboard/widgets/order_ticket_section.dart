import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/kis_manual_order_result.dart';
import '../../../models/order_validation_result.dart';
import '../../dashboard/dashboard_controller.dart';

const int defaultVisibleKisOrderHistoryCount = 3;

class OrderTicketSection extends StatefulWidget {
  const OrderTicketSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<OrderTicketSection> createState() => _OrderTicketSectionState();
}

class _OrderTicketSectionState extends State<OrderTicketSection> {
  static const _pollInterval = Duration(seconds: 20);

  late final TextEditingController _symbolController;
  late final TextEditingController _qtyController;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _symbolController =
        TextEditingController(text: widget.controller.orderTicketSymbol);
    _qtyController =
        TextEditingController(text: widget.controller.orderTicketQtyInput);
    widget.controller.addListener(_handleControllerChanged);
    _updatePolling();
  }

  @override
  void dispose() {
    widget.controller.removeListener(_handleControllerChanged);
    _stopPolling();
    _symbolController.dispose();
    _qtyController.dispose();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant OrderTicketSection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller == widget.controller) return;
    oldWidget.controller.removeListener(_handleControllerChanged);
    widget.controller.addListener(_handleControllerChanged);
    _updatePolling();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    const title = 'KIS Manual Buy/Sell Ticket';
    _syncTextControllers(controller);

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.request_quote_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(title, style: Theme.of(context).textTheme.titleMedium),
          ),
        ]),
        const SizedBox(height: 12),
        _KrOrderTicket(
          controller: controller,
          symbolController: _symbolController,
          qtyController: _qtyController,
        ),
      ]),
    );
  }

  void _syncTextControllers(DashboardController controller) {
    final symbol = controller.orderTicketSymbol;
    if (_symbolController.text != symbol) {
      _symbolController.value = TextEditingValue(
        text: symbol,
        selection: TextSelection.collapsed(offset: symbol.length),
      );
    }

    final qty = controller.orderTicketQtyInput;
    if (_qtyController.text != qty) {
      _qtyController.value = TextEditingValue(
        text: qty,
        selection: TextSelection.collapsed(offset: qty.length),
      );
    }
  }

  void _handleControllerChanged() {
    _updatePolling();
  }

  void _updatePolling() {
    if (!mounted) return;
    if (widget.controller.selectedKisOrderIsPollable) {
      _startPolling();
    } else {
      _stopPolling();
    }
  }

  void _startPolling() {
    if (_pollTimer?.isActive == true) return;
    _pollTimer = Timer.periodic(_pollInterval, (_) async {
      if (!mounted) {
        _stopPolling();
        return;
      }
      final controller = widget.controller;
      if (!controller.selectedKisOrderIsPollable) {
        _stopPolling();
        return;
      }
      await controller.pollSelectedKisOrder();
      if (!mounted || !controller.selectedKisOrderIsPollable) {
        _stopPolling();
      }
    });
  }

  void _stopPolling() {
    _pollTimer?.cancel();
    _pollTimer = null;
  }
}

class _KrOrderTicket extends StatelessWidget {
  const _KrOrderTicket({
    required this.controller,
    required this.symbolController,
    required this.qtyController,
  });

  final DashboardController controller;
  final TextEditingController symbolController;
  final TextEditingController qtyController;

  @override
  Widget build(BuildContext context) {
    final side = controller.orderTicketSide;
    final validateLabel = controller.orderValidationLoading
        ? 'Validating...'
        : 'Validate ${side == 'sell' ? 'Sell' : 'Buy'}';

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: const [
        _SoftBadge(text: 'REAL KIS LIVE', color: Colors.redAccent),
        _SoftBadge(text: 'MANUAL ONLY', color: Colors.lightBlueAccent),
        _SoftBadge(text: 'NO AUTO KIS ORDERS', color: Colors.amberAccent),
      ]),
      const SizedBox(height: 12),
      _RuntimeSafetyStatusCard(controller: controller),
      if (controller.hasPreparedKisManualSellTicket ||
          controller.hasPreparedKisExitSellTicket) ...[
        const SizedBox(height: 12),
        _PreparedManualSellNotice(controller: controller),
      ],
      const SizedBox(height: 12),
      LayoutBuilder(builder: (context, constraints) {
        final vertical = constraints.maxWidth < 620;
        final symbolInput = TextField(
          controller: symbolController,
          decoration: const InputDecoration(
            labelText: 'KR symbol',
            hintText: '005930',
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
          onChanged: controller.setOrderTicketSymbol,
        );
        final qtyInput = TextField(
          controller: qtyController,
          decoration: InputDecoration(
            labelText: 'Qty',
            border: OutlineInputBorder(),
            errorText: controller.isOrderTicketQtyValid
                ? null
                : 'Enter quantity 1 or higher.',
          ),
          keyboardType: TextInputType.number,
          inputFormatters: [FilteringTextInputFormatter.digitsOnly],
          onChanged: controller.setOrderTicketQtyInput,
        );
        final sidePicker = SegmentedButton<String>(
          segments: const [
            ButtonSegment(value: 'buy', label: Text('Buy')),
            ButtonSegment(value: 'sell', label: Text('Sell')),
          ],
          selected: {side},
          onSelectionChanged: (selection) =>
              controller.setOrderTicketSide(selection.first),
        );

        if (vertical) {
          return Column(children: [
            symbolInput,
            const SizedBox(height: 10),
            qtyInput,
            const SizedBox(height: 10),
            Align(alignment: Alignment.centerLeft, child: sidePicker),
          ]);
        }
        return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Expanded(child: symbolInput),
          const SizedBox(width: 10),
          SizedBox(width: 140, child: qtyInput),
          const SizedBox(width: 10),
          sidePicker,
        ]);
      }),
      const SizedBox(height: 10),
      const _StateLine(text: 'Order type: MARKET'),
      const SizedBox(height: 12),
      FilledButton.icon(
        onPressed: controller.orderValidationLoading ||
                !controller.isOrderTicketInputValid
            ? null
            : () async {
                final result = await controller.validateKisOrder();
                if (!context.mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                  content: Text(result.message),
                  backgroundColor:
                      result.success ? Colors.green : Colors.redAccent,
                ));
              },
        icon: controller.orderValidationLoading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2))
            : const Icon(Icons.fact_check_outlined),
        label: Text(validateLabel),
      ),
      const SizedBox(height: 10),
      const _StateLine(text: 'Use dry-run validation first'),
      const SizedBox(height: 12),
      if (controller.orderValidationError != null)
        _RawErrorSection(
          title: 'Validation error details',
          primary: _primaryLine(controller.orderValidationError!),
          raw: controller.orderValidationError!,
        ),
      if (controller.orderValidationResult != null)
        _ValidationResultCard(result: controller.orderValidationResult!),
      const SizedBox(height: 12),
      CheckboxListTile(
        contentPadding: EdgeInsets.zero,
        controlAffinity: ListTileControlAffinity.leading,
        value: controller.kisLiveConfirmation,
        onChanged: controller.kisManualSubmitLoading
            ? null
            : (value) => controller.setKisLiveConfirmation(value == true),
        title: Text(controller.orderTicketSide == 'sell'
            ? 'I understand this may submit a real KIS sell order.'
            : 'I understand this may submit a real KIS buy order.'),
        subtitle: const Text(
          'Manual-only lane; final confirmation is still required before submit.',
        ),
      ),
      const SizedBox(height: 8),
      _PreSubmitChecklist(controller: controller),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: [
        FilledButton.icon(
          onPressed: controller.kisManualSubmitLoading ||
                  controller.orderValidationLoading ||
                  !controller.isOrderTicketInputValid
              ? null
              : () => _handleManualSubmitPressed(context, controller),
          icon: controller.kisManualSubmitLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.send_outlined),
          label: Text(controller.kisManualSubmitLoading
              ? 'Submitting...'
              : controller.orderTicketSide == 'sell'
                  ? 'Submit Manual Sell'
                  : 'Submit Live KIS Order'),
        ),
        if (controller.latestKisManualOrder?.isSyncable == true &&
            controller.latestKisManualOrder?.isTerminal != true)
          OutlinedButton.icon(
            onPressed: controller.kisOrderSyncLoading
                ? null
                : () async {
                    final result = await controller.syncLatestKisOrder();
                    if (!context.mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(result.message),
                      backgroundColor:
                          result.success ? Colors.green : Colors.redAccent,
                    ));
                  },
            icon: controller.kisOrderSyncLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.sync),
            label: Text(
                controller.kisOrderSyncLoading ? 'Syncing...' : 'Sync Status'),
          ),
        OutlinedButton.icon(
          onPressed: controller.kisOrderSyncLoading
              ? null
              : () async {
                  final result = await controller.syncOpenKisOrders();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisOrderSyncLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.cloud_sync_outlined),
          label: Text(controller.kisOrderSyncLoading
              ? 'Syncing...'
              : 'Sync Open KIS Orders'),
        ),
        OutlinedButton.icon(
          onPressed: controller.kisOrdersLoading
              ? null
              : () async {
                  final result = await controller.refreshKisOrders();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisOrdersLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.receipt_long_outlined),
          label: Text(
              controller.kisOrdersLoading ? 'Refreshing...' : 'Refresh Orders'),
        ),
      ]),
      if (controller.kisManualOrderError != null) ...[
        const SizedBox(height: 12),
        _RawErrorSection(
          title: 'Order error details',
          primary: _primaryLine(controller.kisManualOrderError!),
          raw: controller.kisManualOrderErrorRaw ??
              controller.kisManualOrderError!,
        ),
      ],
      const SizedBox(height: 12),
      _KisOrderStatusPanel(
        controller: controller,
        latest: controller.latestKisManualOrder,
        selected: controller.selectedKisOrder,
        orders: controller.kisOrders,
      ),
    ]);
  }
}

class _PreparedManualSellNotice extends StatelessWidget {
  const _PreparedManualSellNotice({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final metadata = controller.orderTicketSourceMetadata ?? const {};
    final trigger = metadata['exit_trigger']?.toString();
    final triggerSource = metadata['trigger_source']?.toString();
    final source = metadata['source']?.toString();
    final sourceType = metadata['source_type']?.toString();
    final fromShadow = metadata['source'] == 'kis_exit_shadow_decision';
    final fromExitPreflight = metadata['source'] == 'kis_live_exit_preflight';
    final subtitle = fromShadow
        ? 'Prepared from exit shadow decision'
        : fromExitPreflight
            ? 'Prepared from exit preflight'
            : 'Prepared Manual Sell';
    final estimated = _preparedEstimatedNotional(controller, metadata);
    final reason = _orderReason(controller);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.greenAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.greenAccent.withValues(alpha: 0.28)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text(
          'KIS Manual SELL Ticket',
          style: TextStyle(
            color: Colors.greenAccent,
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 4),
        Text(subtitle, style: const TextStyle(color: Colors.white70)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          const _SoftBadge(
              text: 'MANUAL CONFIRMATION REQUIRED', color: Colors.greenAccent),
          const _SoftBadge(text: 'NO AUTO SELL', color: Colors.amberAccent),
          const _SoftBadge(
              text: 'VALIDATE BEFORE SUBMIT', color: Colors.lightBlueAccent),
          const _SoftBadge(
              text: 'confirm_live required', color: Colors.redAccent),
          if (fromShadow)
            const _SoftBadge(
                text: 'SHADOW EXIT ONLY', color: Colors.lightBlueAccent),
          if (fromShadow)
            const _SoftBadge(
                text: 'NO MANUAL SUBMIT YET', color: Colors.orangeAccent),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          const _DataPair(label: 'provider', value: 'KIS'),
          const _DataPair(label: 'side', value: 'SELL'),
          _DataPair(label: 'symbol', value: controller.orderTicketSymbol),
          _DataPair(
              label: 'quantity',
              value:
                  (controller.parsedOrderTicketQty ?? controller.orderTicketQty)
                      .toString()),
          _DataPair(label: 'estimated notional', value: estimated),
          _DataPair(label: 'reason', value: reason),
          if (source != null) _DataPair(label: 'source', value: source),
          if (sourceType != null)
            _DataPair(label: 'source_type', value: sourceType),
          if (trigger != null) _DataPair(label: 'trigger', value: trigger),
          if (triggerSource != null)
            _DataPair(label: 'trigger_source', value: triggerSource),
        ]),
      ]),
    );
  }
}

class _RuntimeSafetyStatusCard extends StatelessWidget {
  const _RuntimeSafetyStatusCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.kisSafetyStatus;
    final isSell = controller.orderTicketSide == 'sell';
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
            child: Text('RUNTIME SAFETY STATUS',
                style: TextStyle(
                    color: Colors.white54,
                    fontSize: 10,
                    fontWeight: FontWeight.w800)),
          ),
          IconButton(
            tooltip: 'Refresh KIS safety status',
            onPressed: controller.kisSafetyStatusLoading
                ? null
                : () => controller.refreshKisSafetyStatus(),
            icon: controller.kisSafetyStatusLoading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.refresh, size: 18),
          ),
        ]),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(
              label: 'dry_run', value: status.runtimeDryRun ? 'ON' : 'OFF'),
          _DataPair(
              label: 'kill_switch', value: status.killSwitch ? 'ON' : 'OFF'),
          _DataPair(label: 'kis_enabled', value: status.kisEnabled.toString()),
          _DataPair(
              label: 'kis_real_order_enabled',
              value: status.kisRealOrderEnabled.toString()),
          _DataPair(label: 'market_open', value: status.marketOpen.toString()),
          if (isSell)
            _DataPair(
                label: 'sell_session_allowed',
                value: status.marketOpen.toString())
          else ...[
            _DataPair(
                label: 'entry_allowed_now',
                value: status.entryAllowedNow.toString()),
            _DataPair(
                label: 'no_new_entry_after', value: status.noNewEntryAfter),
          ],
        ]),
        const SizedBox(height: 10),
        _StateLine(
          text: controller.kisRuntimeLiveSubmitMessage(),
          color: controller.kisCurrentOrderRuntimeGatesOpen
              ? Colors.greenAccent
              : Colors.redAccent,
        ),
      ]),
    );
  }
}

class _PreSubmitChecklist extends StatelessWidget {
  const _PreSubmitChecklist({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final validation = controller.orderValidationResult;
    final status = controller.kisSafetyStatus;
    final symbolMatches =
        validation?.symbol == controller.orderTicketSymbol.trim();
    final currentQty = controller.parsedOrderTicketQty;
    final qtyMatches = currentQty != null && validation?.qty == currentQty;
    final sideMatches = validation?.side == controller.orderTicketSide;
    final validationMatchesCurrent =
        validation != null && symbolMatches && qtyMatches && sideMatches;
    final inputValid = controller.isOrderTicketInputValid;
    final items = [
      _ChecklistItem(
          label: 'recent validation passed',
          passed: validation?.validatedForSubmission == true),
      _ChecklistItem(
          label: 'validation matches current symbol / qty / side',
          passed: validationMatchesCurrent),
      _ChecklistItem(
          label: 'confirm_live checked',
          passed: controller.kisLiveConfirmation),
      _ChecklistItem(
          label: 'runtime dry_run is OFF', passed: !status.runtimeDryRun),
      _ChecklistItem(label: 'kill_switch is OFF', passed: !status.killSwitch),
      _ChecklistItem(label: 'KIS enabled', passed: status.kisEnabled),
      _ChecklistItem(
          label: 'KIS real order enabled', passed: status.kisRealOrderEnabled),
      _ChecklistItem(label: 'market open', passed: status.marketOpen),
      _ChecklistItem(
          label: controller.currentOrderRequiresEntryWindow
              ? 'market entry allowed'
              : 'sell session allowed',
          passed: controller.currentOrderRequiresEntryWindow
              ? status.entryAllowedNow
              : status.marketOpen),
      _ChecklistItem(label: 'qty and symbol valid', passed: inputValid),
    ];

    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('PRE-SUBMIT CHECKLIST',
            style: TextStyle(
                color: Colors.white54,
                fontSize: 10,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: items),
      ]),
    );
  }
}

class _ChecklistItem extends StatelessWidget {
  const _ChecklistItem({required this.label, required this.passed});

  final String label;
  final bool passed;

  @override
  Widget build(BuildContext context) {
    return _SoftBadge(
      text: '${passed ? '✓' : '×'} $label',
      color: passed ? Colors.greenAccent : Colors.redAccent,
    );
  }
}

class _RawErrorSection extends StatelessWidget {
  const _RawErrorSection({
    required this.title,
    required this.primary,
    required this.raw,
  });

  final String title;
  final String primary;
  final String raw;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      _StateLine(text: primary, color: Colors.redAccent),
      ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: EdgeInsets.zero,
        title: Text(title),
        children: [_StateLine(text: raw)],
      ),
    ]);
  }
}

class _KisOrderStatusPanel extends StatelessWidget {
  const _KisOrderStatusPanel({
    required this.controller,
    required this.latest,
    required this.selected,
    required this.orders,
  });

  final DashboardController controller;
  final KisManualOrderResult? latest;
  final KisManualOrderResult? selected;
  final List<KisManualOrderResult> orders;

  @override
  Widget build(BuildContext context) {
    final detail = selected ?? latest;
    final history = controller.visibleKisOrders
        .where((order) => order.orderId != detail?.orderId)
        .toList();
    final visibleHistory =
        history.take(defaultVisibleKisOrderHistoryCount).toList();
    final olderHistory =
        history.skip(defaultVisibleKisOrderHistoryCount).toList();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Expanded(
            child: Text('KIS ORDER STATUS',
                style: TextStyle(
                    color: Colors.white54,
                    fontSize: 10,
                    fontWeight: FontWeight.w800)),
          ),
          if (detail != null) _ClearStatusPill(order: detail),
        ]),
        const SizedBox(height: 10),
        _KisTodaySummaryCard(summary: controller.kisOrderSummary),
        const SizedBox(height: 10),
        _KisOrderHistoryControls(controller: controller),
        const SizedBox(height: 10),
        if (detail == null)
          const _StateLine(text: 'No recent KIS manual live orders')
        else ...[
          Wrap(spacing: 14, runSpacing: 8, children: [
            _DataPair(label: 'Order ID', value: detail.orderId.toString()),
            _DataPair(label: 'ODNO', value: detail.kisOdno ?? 'n/a'),
            _DataPair(label: 'Symbol', value: detail.symbol),
            _DataPair(label: 'Side', value: detail.side.toUpperCase()),
            _DataPair(
                label: 'Requested',
                value: _nullableQuantity(detail.requestedQty)),
            _DataPair(label: 'Filled', value: _quantity(detail.filledQty)),
            _DataPair(
                label: 'Remaining',
                value: _nullableQuantity(detail.remainingQty)),
            _DataPair(
                label: 'Avg Fill',
                value: detail.avgFillPrice == null
                    ? 'n/a'
                    : _krw(detail.avgFillPrice!)),
            _DataPair(label: 'Internal Status', value: detail.internalStatus),
            _DataPair(
                label: 'Broker Status',
                value: detail.brokerOrderStatus ?? 'n/a'),
            _DataPair(label: 'Created', value: detail.createdAt ?? 'n/a'),
            _DataPair(label: 'Last Sync', value: detail.lastSyncedAt ?? 'n/a'),
            _DataPair(label: 'State', value: _syncState(detail)),
          ]),
          const SizedBox(height: 10),
          _OrderTimeline(order: detail),
          const SizedBox(height: 10),
          Align(
            alignment: Alignment.centerLeft,
            child: _ClearStatusPill(order: detail),
          ),
          if (!detail.isTerminal && detail.isSyncable) ...[
            const SizedBox(height: 10),
            Wrap(spacing: 8, runSpacing: 8, children: [
              OutlinedButton.icon(
                onPressed: controller.kisOrderSyncLoading
                    ? null
                    : () async {
                        final result =
                            await controller.syncKisOrderById(detail.orderId);
                        if (!context.mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                          content: Text(result.message),
                          backgroundColor:
                              result.success ? Colors.green : Colors.redAccent,
                        ));
                      },
                icon: const Icon(Icons.sync),
                label: const Text('Sync Status'),
              ),
              if (detail.canCancel)
                OutlinedButton.icon(
                  onPressed: controller.kisOrderCancelLoading
                      ? null
                      : () async {
                          final confirmed =
                              await _confirmCancelKisOrder(context);
                          if (!confirmed || !context.mounted) return;
                          final result = await controller
                              .cancelKisOrderById(detail.orderId);
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text(result.message),
                            backgroundColor: result.success
                                ? Colors.green
                                : Colors.redAccent,
                          ));
                        },
                  icon: controller.kisOrderCancelLoading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.cancel_outlined),
                  label: const Text('Cancel Order'),
                ),
            ]),
          ],
          if (detail.brokerOrderStatus != null) ...[
            const SizedBox(height: 10),
            _StateLine(text: 'Broker status: ${detail.brokerOrderStatus}'),
          ],
          if (detail.hasSyncError) ...[
            const SizedBox(height: 10),
            _StateLine(text: detail.syncError!, color: Colors.amberAccent),
          ],
        ],
        if (history.isNotEmpty) ...[
          const SizedBox(height: 14),
          const Text('ORDER HISTORY',
              style: TextStyle(
                  color: Colors.white54,
                  fontSize: 10,
                  fontWeight: FontWeight.w800)),
          const SizedBox(height: 8),
          for (final order in visibleHistory)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _RecentKisOrderRow(order: order, controller: controller),
            ),
          if (olderHistory.isNotEmpty)
            ExpansionTile(
              tilePadding: EdgeInsets.zero,
              childrenPadding: EdgeInsets.zero,
              title: Text('Older order history (${olderHistory.length})'),
              children: [
                for (final order in olderHistory)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: _RecentKisOrderRow(
                        order: order, controller: controller),
                  ),
              ],
            ),
        ],
      ]),
    );
  }
}

class _KisTodaySummaryCard extends StatelessWidget {
  const _KisTodaySummaryCard({required this.summary});

  final KisOrderSummary summary;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('KIS TODAY',
            style: TextStyle(
                color: Colors.white54,
                fontSize: 10,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(label: 'Open Orders', value: summary.openOrders.toString()),
          _DataPair(label: 'Filled', value: summary.filledToday.toString()),
          _DataPair(label: 'Canceled', value: summary.canceledToday.toString()),
          _DataPair(label: 'Rejected', value: summary.rejectedToday.toString()),
        ]),
      ]),
    );
  }
}

class _KisOrderHistoryControls extends StatelessWidget {
  const _KisOrderHistoryControls({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: [
        for (final filter in KisOrderHistoryFilter.values)
          ChoiceChip(
            label: Text(_filterLabel(filter)),
            selected: controller.kisOrderFilter == filter,
            onSelected: (_) => controller.setKisOrderFilter(filter),
          ),
      ]),
      const SizedBox(height: 8),
      SegmentedButton<KisOrderHistorySort>(
        segments: const [
          ButtonSegment(
            value: KisOrderHistorySort.newestFirst,
            label: Text('Newest first'),
          ),
          ButtonSegment(
            value: KisOrderHistorySort.oldestFirst,
            label: Text('Oldest first'),
          ),
        ],
        selected: {controller.kisOrderSort},
        onSelectionChanged: (selection) =>
            controller.setKisOrderSort(selection.first),
      ),
    ]);
  }
}

class _RecentKisOrderRow extends StatelessWidget {
  const _RecentKisOrderRow({required this.order, required this.controller});

  final KisManualOrderResult order;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final title = _compactOrderTitle(order);
    final subtitle = _compactOrderSubtitle(order);
    return InkWell(
      key: ValueKey('kis-order-history-row-${order.orderId}'),
      onTap: () => controller.selectKisOrder(order.orderId),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.04),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(children: [
            Expanded(
              child: Text(
                title,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: Colors.white70, fontWeight: FontWeight.w700),
              ),
            ),
            const SizedBox(width: 8),
            _ClearStatusPill(order: order),
          ]),
          const SizedBox(height: 4),
          Text(
            subtitle,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
          const SizedBox(height: 8),
          Wrap(spacing: 8, runSpacing: 8, children: [
            _SoftBadge(
              text: order.side.toUpperCase() == 'SELL' ? 'SELL' : 'BUY',
              color: order.side.toUpperCase() == 'SELL'
                  ? Colors.orangeAccent
                  : Colors.lightBlueAccent,
            ),
            _SoftBadge(
              text: 'FILLED ${_quantity(order.filledQty)}',
              color: order.filledQty > 0 ? Colors.greenAccent : Colors.white54,
            ),
            if (order.brokerOrderStatus?.isNotEmpty == true)
              _SoftBadge(
                text: order.brokerOrderStatus!.toUpperCase(),
                color: Colors.white70,
              ),
          ]),
          if (!order.isTerminal && order.isSyncable) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 8, runSpacing: 8, children: [
              IconButton(
                tooltip: 'Sync KIS order status',
                onPressed: controller.kisOrderSyncLoading
                    ? null
                    : () async {
                        await controller.selectKisOrder(order.orderId);
                        await controller.syncKisOrderById(order.orderId);
                      },
                icon: const Icon(Icons.sync, size: 18),
              ),
              if (order.canCancel)
                IconButton(
                  tooltip: 'Cancel KIS order',
                  onPressed: controller.kisOrderCancelLoading
                      ? null
                      : () async {
                          final confirmed =
                              await _confirmCancelKisOrder(context);
                          if (!confirmed || !context.mounted) return;
                          final result = await controller
                              .cancelKisOrderById(order.orderId);
                          if (!context.mounted) return;
                          ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                            content: Text(result.message),
                            backgroundColor: result.success
                                ? Colors.green
                                : Colors.redAccent,
                          ));
                        },
                  icon: const Icon(Icons.cancel_outlined, size: 18),
                ),
            ]),
          ],
        ]),
      ),
    );
  }
}

class _ClearStatusPill extends StatelessWidget {
  const _ClearStatusPill({required this.order});

  final KisManualOrderResult order;

  @override
  Widget build(BuildContext context) {
    final status = order.clearStatusLabel;
    final color = switch (status) {
      'FILLED' => Colors.greenAccent,
      'CANCELED' => Colors.lightBlueAccent,
      'REJECTED' => Colors.redAccent,
      'SUBMITTED' => Colors.amberAccent,
      _ => Colors.white54,
    };
    return _SoftBadge(text: status, color: color);
  }
}

class _OrderTimeline extends StatelessWidget {
  const _OrderTimeline({required this.order});

  final KisManualOrderResult order;

  @override
  Widget build(BuildContext context) {
    final stages = [
      _TimelineStage('VALIDATED', order.validatedAt),
      _TimelineStage('SUBMITTED', order.submittedAt),
      _TimelineStage('SYNCED', order.lastSyncedAt),
      _TimelineStage('FILLED', order.filledAt),
      _TimelineStage('CANCELED', order.canceledAt),
      _TimelineStage('REJECTED', order.rejectedAt),
    ];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const Text('LIFECYCLE TIMELINE',
            style: TextStyle(
                color: Colors.white54,
                fontSize: 10,
                fontWeight: FontWeight.w800)),
        const SizedBox(height: 8),
        Wrap(spacing: 8, runSpacing: 8, children: [
          for (final stage in stages)
            _SoftBadge(
              text: '${stage.label}: ${stage.timestamp ?? 'n/a'}',
              color: stage.timestamp == null
                  ? Colors.white38
                  : Colors.lightBlueAccent,
            ),
        ]),
      ]),
    );
  }
}

class _TimelineStage {
  const _TimelineStage(this.label, this.timestamp);

  final String label;
  final String? timestamp;
}

class _ValidationResultCard extends StatelessWidget {
  const _ValidationResultCard({required this.result});

  final OrderValidationResult result;

  @override
  Widget build(BuildContext context) {
    final blocked = !result.validatedForSubmission;
    final isSell = result.side.toLowerCase() == 'sell';
    final closureLabel = result.marketSession.closureName?.isNotEmpty == true
        ? result.marketSession.closureName!
        : result.marketSession.closureReason;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          _SoftBadge(
            text: blocked ? 'BLOCKED BY VALIDATION' : 'DRY-RUN VALIDATED',
            color: blocked ? Colors.redAccent : Colors.greenAccent,
          ),
          const SizedBox(width: 8),
          const _SoftBadge(
              text: 'NO REAL ORDER SUBMITTED', color: Colors.lightBlueAccent),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(label: 'Symbol', value: result.symbol),
          _DataPair(label: 'Side', value: result.side.toUpperCase()),
          _DataPair(label: 'Qty', value: result.qty.toString()),
          if (result.currentPrice != null)
            _DataPair(
                label: 'Current Price', value: _krw(result.currentPrice!)),
          if (result.estimatedAmount != null)
            _DataPair(
                label: 'Estimated Amount',
                value: _krw(result.estimatedAmount!)),
          if (result.availableCash != null)
            _DataPair(
                label: 'Available Cash', value: _krw(result.availableCash!)),
          if (result.heldQty != null)
            _DataPair(label: 'Held Qty', value: _quantity(result.heldQty!)),
          if (closureLabel != null && closureLabel.isNotEmpty)
            _DataPair(label: 'Closed Reason', value: closureLabel),
          if (result.marketSession.effectiveClose?.isNotEmpty == true)
            _DataPair(
                label: 'Effective Close',
                value: result.marketSession.effectiveClose!),
          if (!isSell &&
              result.marketSession.noNewEntryAfter?.isNotEmpty == true)
            _DataPair(
                label: 'No New Entry After',
                value: result.marketSession.noNewEntryAfter!),
          _DataPair(
              label: 'Account',
              value: result.orderPreview.accountNoMasked.isEmpty
                  ? 'n/a'
                  : result.orderPreview.accountNoMasked),
          _DataPair(
              label: 'TR ID',
              value: result.orderPreview.kisTrIdPreview.isEmpty
                  ? 'n/a'
                  : result.orderPreview.kisTrIdPreview),
        ]),
        const SizedBox(height: 12),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _SoftBadge(
              text: result.marketSession.isMarketOpen
                  ? 'MARKET OPEN'
                  : 'MARKET CLOSED',
              color: result.marketSession.isMarketOpen
                  ? Colors.greenAccent
                  : Colors.redAccent),
          if (isSell)
            _SoftBadge(
                text: result.marketSession.isMarketOpen
                    ? 'SELL SESSION ALLOWED'
                    : 'SELL SESSION BLOCKED',
                color: result.marketSession.isMarketOpen
                    ? Colors.greenAccent
                    : Colors.amberAccent)
          else
            _SoftBadge(
                text: result.marketSession.isEntryAllowedNow
                    ? 'ENTRY ALLOWED'
                    : 'ENTRY BLOCKED',
                color: result.marketSession.isEntryAllowedNow
                    ? Colors.greenAccent
                    : Colors.amberAccent),
          if (result.marketSession.isNearClose)
            const _SoftBadge(text: 'NEAR CLOSE', color: Colors.amberAccent),
        ]),
        if (!result.marketSession.isMarketOpen && closureLabel != null) ...[
          const SizedBox(height: 10),
          _StateLine(text: 'Market closed: $closureLabel'),
        ],
        if (blocked && result.message?.isNotEmpty == true) ...[
          const SizedBox(height: 12),
          _StateLine(text: result.message!, color: Colors.redAccent),
        ],
        const SizedBox(height: 12),
        _ValidationDetailSection(result: result),
      ]),
    );
  }
}

class _ValidationDetailSection extends StatelessWidget {
  const _ValidationDetailSection({required this.result});

  final OrderValidationResult result;

  @override
  Widget build(BuildContext context) {
    final lines = <String>[
      if (result.primaryBlockReason?.isNotEmpty == true)
        'Primary: ${result.primaryBlockReason}',
      if (result.warnings.isNotEmpty) 'Warnings: ${result.warnings.join(', ')}',
      if (result.blockReasons.isNotEmpty)
        'Block reasons: ${result.blockReasons.join(', ')}',
      if (result.detail.isNotEmpty) 'Detail: ${jsonEncode(result.detail)}',
      'Payload preview: ${jsonEncode(result.orderPreview.payloadPreview)}',
    ];

    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text('Raw validation details'),
      children: [
        _StateLine(text: lines.join('\n')),
      ],
    );
  }
}

class _DataPair extends StatelessWidget {
  const _DataPair({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 112, maxWidth: 190),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(label.toUpperCase(),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white54,
                fontSize: 10,
                fontWeight: FontWeight.w700)),
        const SizedBox(height: 3),
        Text(value,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
                color: Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _StateLine extends StatelessWidget {
  const _StateLine({required this.text, this.color = Colors.white60});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.04),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
      ),
      child: Text(text, style: TextStyle(color: color)),
    );
  }
}

class _SoftBadge extends StatelessWidget {
  const _SoftBadge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.34)),
      ),
      child: Text(text,
          style: TextStyle(
              color: color, fontSize: 11, fontWeight: FontWeight.w800)),
    );
  }
}

String _krw(double value) {
  final sign = value < 0 ? '-' : '';
  return '$sign₩${_groupedNumber(value.abs().round())}';
}

String _groupedNumber(int value) {
  final text = value.toString();
  final buffer = StringBuffer();
  for (var i = 0; i < text.length; i += 1) {
    final remaining = text.length - i;
    buffer.write(text[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  return buffer.toString();
}

String _krwDisplay(double value) {
  final sign = value < 0 ? '-' : '';
  return '${sign}KRW ${_groupedNumber(value.abs().round())}';
}

String _formatPct(double value) {
  return '${(value * 100).toStringAsFixed(2)}%';
}

String _displaySymbolCompany(String symbol, String? companyName) {
  final normalizedSymbol = symbol.trim();
  final name = companyName?.trim() ?? '';
  if (name.isEmpty) return normalizedSymbol;
  final lower = name.toLowerCase();
  if (lower == 'unknown' || lower == 'unknown company') {
    return normalizedSymbol;
  }
  if (name == normalizedSymbol) return normalizedSymbol;
  return '$normalizedSymbol - $name';
}

List<String> _dedupe(List<String> values) {
  final result = <String>[];
  for (final value in values) {
    final text = value.trim();
    if (text.isEmpty || result.contains(text)) continue;
    result.add(text);
  }
  return result;
}

String _quantity(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value
      .toStringAsFixed(6)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
}

String _nullableQuantity(double? value) {
  if (value == null) return 'n/a';
  return _quantity(value);
}

String _primaryLine(String value) {
  final lines = value
      .split(RegExp(r'[\r\n]+'))
      .map((line) => line.trim())
      .where((line) => line.isNotEmpty);
  return lines.isEmpty ? value.trim() : lines.first;
}

String _syncState(KisManualOrderResult order) {
  if (order.isTerminal) return 'terminal';
  if (order.isSyncable) return 'syncable';
  return 'non-syncable';
}

String _compactOrderTitle(KisManualOrderResult order) {
  final name = _orderDisplayName(order);
  final side = order.side.toUpperCase() == 'SELL' ? 'SELL' : 'BUY';
  final qty = _nullableQuantity(order.requestedQty);
  return '$name · $side $qty · ${order.clearStatusLabel}';
}

String _compactOrderSubtitle(KisManualOrderResult order) {
  return '${order.symbol} · ${_orderIdentifier(order)} · ${_compactKstTime(order.createdAt)}';
}

String _orderDisplayName(KisManualOrderResult order) {
  final direct = order.companyName;
  if (direct != null && direct.trim().isNotEmpty) return direct.trim();
  final metadata = order.sourceMetadata;
  final metadataName = metadata['company_name'] ?? metadata['name'];
  if (metadataName != null && metadataName.toString().trim().isNotEmpty) {
    return metadataName.toString().trim();
  }
  final snapshot = metadata['position_snapshot'];
  if (snapshot is Map) {
    final snapshotName = snapshot['company_name'] ?? snapshot['name'];
    if (snapshotName != null && snapshotName.toString().trim().isNotEmpty) {
      return snapshotName.toString().trim();
    }
  }
  return order.symbol;
}

String _orderIdentifier(KisManualOrderResult order) {
  final odno = order.kisOdno?.trim();
  if (odno != null && odno.isNotEmpty) return 'ODNO $odno';
  return 'ODNO n/a';
}

String _compactKstTime(String? value) {
  final text = value?.trim();
  if (text == null || text.isEmpty) return 'KST n/a';
  final parsed = DateTime.tryParse(text);
  if (parsed == null) return 'KST $text';
  final kst =
      parsed.isUtc ? parsed.toUtc().add(const Duration(hours: 9)) : parsed;
  final hour = kst.hour.toString().padLeft(2, '0');
  final minute = kst.minute.toString().padLeft(2, '0');
  return 'KST $hour:$minute';
}

String _filterLabel(KisOrderHistoryFilter filter) {
  return switch (filter) {
    KisOrderHistoryFilter.open => 'OPEN',
    KisOrderHistoryFilter.filled => 'FILLED',
    KisOrderHistoryFilter.canceled => 'CANCELED',
    KisOrderHistoryFilter.rejected => 'REJECTED',
    KisOrderHistoryFilter.all => 'ALL',
  };
}

Future<bool> _confirmCancelKisOrder(BuildContext context) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Cancel Order'),
      content: const Text(
        'Cancel this KIS order? This only cancels the existing open order and will not create a new order.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(false),
          child: const Text('Keep Order'),
        ),
        FilledButton(
          onPressed: () => Navigator.of(context).pop(true),
          child: const Text('Cancel Order'),
        ),
      ],
    ),
  );
  return confirmed == true;
}

Future<void> _handleManualSubmitPressed(
  BuildContext context,
  DashboardController controller,
) async {
  if (controller.orderValidationResult == null ||
      !controller.orderValidationMatchesCurrent) {
    final validationResult = await controller.validateKisOrder();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(validationResult.message),
      backgroundColor:
          validationResult.success ? Colors.green : Colors.redAccent,
    ));
    if (controller.orderValidationResult == null) return;
  }

  while (context.mounted) {
    final action = await showKisLiveOrderConfirmationDialog(
      context,
      controller: controller,
      validation: controller.orderValidationResult,
      symbol: controller.orderTicketSymbol,
      side: controller.orderTicketSide,
      qty: controller.parsedOrderTicketQty ?? 0,
      confirmLive: controller.kisLiveConfirmation,
      companyName: _orderCompanyName(controller),
      reason: _orderReason(controller),
    );
    if (!context.mounted || action == KisLiveOrderConfirmationAction.cancel) {
      return;
    }
    if (action == KisLiveOrderConfirmationAction.revalidate) {
      final validationResult = await controller.validateKisOrder();
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
        content: Text(validationResult.message),
        backgroundColor:
            validationResult.success ? Colors.green : Colors.redAccent,
      ));
      if (controller.orderValidationResult == null) return;
      continue;
    }

    final result = await controller.submitKisManualOrder();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
      content: Text(result.message),
      backgroundColor: result.success ? Colors.green : Colors.redAccent,
    ));
    return;
  }
}

enum KisLiveOrderConfirmationAction { cancel, submit, revalidate }

Future<KisLiveOrderConfirmationAction> showKisLiveOrderConfirmationDialog(
  BuildContext context, {
  required DashboardController controller,
  required OrderValidationResult? validation,
  required String symbol,
  required String side,
  required int qty,
  required bool confirmLive,
  String? companyName,
  String? reason,
  bool allowRevalidate = true,
}) async {
  final normalizedSide = side.trim().toLowerCase() == 'sell' ? 'SELL' : 'BUY';
  final submitEnabled = _liveOrderSubmitEnabled(
    validation: validation,
    status: controller.kisSafetyStatus,
    side: normalizedSide.toLowerCase(),
    confirmLive: confirmLive,
  );
  final action = await showDialog<KisLiveOrderConfirmationAction>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text('Confirm KIS Live $normalizedSide'),
      content: _KisLiveOrderConfirmationContent(
        controller: controller,
        validation: validation,
        symbol: symbol,
        side: normalizedSide,
        qty: qty,
        confirmLive: confirmLive,
        submitEnabled: submitEnabled,
        companyName: companyName,
        reason: reason,
      ),
      actions: [
        TextButton(
          onPressed: () =>
              Navigator.of(context).pop(KisLiveOrderConfirmationAction.cancel),
          child: const Text('Cancel'),
        ),
        if (allowRevalidate && validation?.isValidationExpired == true)
          OutlinedButton(
            onPressed: () => Navigator.of(context)
                .pop(KisLiveOrderConfirmationAction.revalidate),
            child: const Text('Re-validate'),
          ),
        FilledButton(
          key: const Key('kis_live_order_dialog_submit_button'),
          onPressed: submitEnabled
              ? () => Navigator.of(context)
                  .pop(KisLiveOrderConfirmationAction.submit)
              : null,
          child: const Text('Submit Live Order'),
        ),
      ],
    ),
  );
  return action ?? KisLiveOrderConfirmationAction.cancel;
}

bool _liveOrderSubmitEnabled({
  required OrderValidationResult? validation,
  required dynamic status,
  required String side,
  required bool confirmLive,
}) {
  if (validation == null || validation.isValidationExpired) return false;
  final requiresEntryWindow = side.trim().toLowerCase() != 'sell';
  return confirmLive &&
      validation.validatedForSubmission &&
      validation.effectiveSubmitAllowed &&
      status.runtimeDryRun != true &&
      status.killSwitch != true &&
      status.kisEnabled == true &&
      status.kisRealOrderEnabled == true &&
      status.marketOpen == true &&
      (!requiresEntryWindow || status.entryAllowedNow == true);
}

class _KisLiveOrderConfirmationContent extends StatelessWidget {
  const _KisLiveOrderConfirmationContent({
    required this.controller,
    required this.validation,
    required this.symbol,
    required this.side,
    required this.qty,
    required this.confirmLive,
    required this.submitEnabled,
    this.companyName,
    this.reason,
  });

  final DashboardController controller;
  final OrderValidationResult? validation;
  final String symbol;
  final String side;
  final int qty;
  final bool confirmLive;
  final bool submitEnabled;
  final String? companyName;
  final String? reason;

  @override
  Widget build(BuildContext context) {
    final status = controller.kisSafetyStatus;
    final isSell = side == 'SELL';
    final estimatedPrice =
        validation?.estimatedPrice ?? validation?.currentPrice;
    final estimatedNotional =
        validation?.estimatedNotional ?? validation?.estimatedAmount;
    final availableCash = validation?.availableCash;
    final runtimeDryRun = validation?.runtimeDryRun ?? status.runtimeDryRun;
    final killSwitch = validation?.killSwitch ?? status.killSwitch;
    final kisRealOrderEnabled =
        validation?.kisRealOrderEnabled ?? status.kisRealOrderEnabled;
    final dailyRemaining = validation?.dailyLiveOrderRemaining;
    final maxNotionalPct = validation?.maxOrderNotionalPct ??
        controller.settings.maxOrderNotionalPct;
    final operationMode = validation?.currentOperationMode ??
        controller.settings.currentOperationMode;
    final riskFlags = _dedupe([
      ...?validation?.riskFlags,
      ...?validation?.warnings,
    ]);
    final gatingNotes = _dedupe([
      ...?validation?.gatingNotes,
      ...?validation?.blockReasons,
      if (!confirmLive) 'confirm_live_required',
      if (validation?.isValidationExpired == true) 'validation_stale',
      if (!submitEnabled &&
          identical(controller.orderValidationResult, validation) &&
          controller.kisSubmitBlockedMessage().isNotEmpty)
        controller.kisSubmitBlockedMessage(),
    ]);
    final blocked = validation == null ||
        validation?.isValidationExpired == true ||
        validation?.effectiveSubmitAllowed == false ||
        runtimeDryRun ||
        killSwitch ||
        !kisRealOrderEnabled;

    return SizedBox(
      width: 540,
      child: SingleChildScrollView(
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Wrap(spacing: 8, runSpacing: 8, children: [
            const _SoftBadge(text: 'LIVE ORDER', color: Colors.redAccent),
            const _SoftBadge(
                text: 'MANUAL ONLY', color: Colors.lightBlueAccent),
            if (submitEnabled)
              const _SoftBadge(
                  text: 'BROKER SUBMIT POSSIBLE', color: Colors.redAccent),
            _SoftBadge(
              text: isSell ? 'SELL ORDER' : 'BUY ORDER',
              color: isSell ? Colors.orangeAccent : Colors.redAccent,
            ),
            if (runtimeDryRun)
              const _SoftBadge(text: 'DRY RUN', color: Colors.amberAccent),
            if (blocked)
              const _SoftBadge(text: 'BLOCKED', color: Colors.redAccent),
          ]),
          const SizedBox(height: 12),
          _StateLine(
            text: isSell
                ? 'This is a live KIS SELL order. It may close or reduce a real broker position.'
                : 'This is a live KIS BUY order. It may use real cash in your broker account.',
            color: Colors.redAccent,
          ),
          const SizedBox(height: 12),
          Wrap(spacing: 14, runSpacing: 8, children: [
            const _DataPair(label: 'Broker', value: 'KIS / KR'),
            _DataPair(
              label: 'Symbol',
              value: _displaySymbolCompany(
                symbol,
                companyName?.trim().isNotEmpty == true
                    ? companyName
                    : validation?.companyName,
              ),
            ),
            _DataPair(label: 'Side', value: side),
            _DataPair(label: 'Quantity', value: qty.toString()),
            _DataPair(
              label: 'Estimated price',
              value:
                  estimatedPrice == null ? 'n/a' : _krwDisplay(estimatedPrice),
            ),
            _DataPair(
              label: 'Estimated notional',
              value: estimatedNotional == null
                  ? 'n/a'
                  : _krwDisplay(estimatedNotional),
            ),
            _DataPair(
              label: 'Available cash',
              value: availableCash == null ? 'n/a' : _krwDisplay(availableCash),
            ),
            _DataPair(label: 'Operation mode', value: operationMode),
            _DataPair(label: 'Dry-run', value: runtimeDryRun ? 'ON' : 'OFF'),
            _DataPair(label: 'Kill switch', value: killSwitch ? 'ON' : 'OFF'),
            _DataPair(
              label: 'KIS real orders',
              value: kisRealOrderEnabled ? 'ENABLED' : 'DISABLED',
            ),
            _DataPair(
              label: 'Daily remaining',
              value: dailyRemaining?.toString() ?? 'n/a',
            ),
            _DataPair(
              label: 'Max notional',
              value: _formatPct(maxNotionalPct),
            ),
            _DataPair(
              label: 'Validation',
              value:
                  validation?.validationFreshnessLabel ?? 'Validation not run',
            ),
            _DataPair(
              label: 'Warning level',
              value: validation?.warningLevel ?? 'n/a',
            ),
            const _DataPair(label: 'Manual-only', value: 'YES'),
            if (reason?.trim().isNotEmpty == true)
              _DataPair(label: 'Reason', value: reason!.trim()),
          ]),
          const SizedBox(height: 12),
          _DialogSection(
            title: 'Risk flags',
            values: riskFlags,
            fallback: 'none',
          ),
          const SizedBox(height: 8),
          _DialogSection(
            title: 'Gating notes',
            values: gatingNotes,
            fallback: 'none',
          ),
          if (!confirmLive) ...[
            const SizedBox(height: 8),
            const _StateLine(
              text: 'confirm_live is not checked.',
              color: Colors.amberAccent,
            ),
          ],
        ]),
      ),
    );
  }
}

class _DialogSection extends StatelessWidget {
  const _DialogSection({
    required this.title,
    required this.values,
    required this.fallback,
  });

  final String title;
  final List<String> values;
  final String fallback;

  @override
  Widget build(BuildContext context) {
    final text = values.isEmpty ? fallback : values.join('\n');
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title.toUpperCase(),
          style: const TextStyle(
              color: Colors.white54,
              fontSize: 10,
              fontWeight: FontWeight.w800)),
      const SizedBox(height: 4),
      _StateLine(text: text),
    ]);
  }
}

String _preparedEstimatedNotional(
  DashboardController controller,
  Map<dynamic, dynamic> metadata,
) {
  final validationAmount = controller.orderValidationResult?.estimatedAmount;
  if (validationAmount != null) return _krw(validationAmount);

  final direct = _doubleValue(
    metadata['estimated_amount'] ??
        metadata['estimated_notional'] ??
        metadata['current_value'],
  );
  if (direct != null) return _krw(direct);

  final price = _doubleValue(metadata['current_price']);
  final quantity = controller.parsedOrderTicketQty ?? controller.orderTicketQty;
  if (price != null && quantity > 0) return _krw(price * quantity);

  final snapshot = metadata['position_snapshot'];
  if (snapshot is Map) {
    final snapshotAmount = _doubleValue(
      snapshot['estimated_amount'] ?? snapshot['current_value'],
    );
    if (snapshotAmount != null) return _krw(snapshotAmount);
  }
  return 'n/a';
}

String _orderCompanyName(DashboardController controller) {
  final metadata = controller.orderTicketSourceMetadata ?? const {};
  final direct = metadata['company_name'] ?? metadata['name'];
  if (direct != null && direct.toString().trim().isNotEmpty) {
    return direct.toString().trim();
  }
  final snapshot = metadata['position_snapshot'];
  if (snapshot is Map) {
    final value = snapshot['company_name'] ?? snapshot['name'];
    if (value != null && value.toString().trim().isNotEmpty) {
      return value.toString().trim();
    }
  }
  return controller
          .kisManagedPositionForSymbol(controller.orderTicketSymbol)
          ?.companyName ??
      '';
}

String _orderReason(DashboardController controller) {
  final metadata = controller.orderTicketSourceMetadata ?? const {};
  final reason = metadata['exit_reason'] ?? metadata['reason'];
  if (reason != null && reason.toString().trim().isNotEmpty) {
    return _humanReason(reason.toString());
  }
  final managed =
      controller.kisManagedPositionForSymbol(controller.orderTicketSymbol);
  if (managed != null) return managed.humanReason;
  return controller.orderTicketSide == 'sell'
      ? 'Operator-confirmed position exit'
      : 'Operator-confirmed manual order';
}

String _humanReason(String value) {
  switch (value) {
    case 'stop_loss_triggered':
      return 'Stop-loss threshold reached';
    case 'take_profit_triggered':
      return 'Take-profit threshold reached';
    case 'weak_trend_triggered':
      return 'Weak trend detected';
    case 'sell_pressure_triggered':
      return 'Sell pressure is elevated';
    case 'operator_selected_position_exit':
      return 'Operator-selected position exit';
    default:
      return value.replaceAll('_', ' ');
  }
}

double? _doubleValue(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty || text == 'null') return null;
  return double.tryParse(text);
}
