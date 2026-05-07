import 'dart:convert';
import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/kis_manual_order_result.dart';
import '../../../models/order_validation_result.dart';
import '../../dashboard/dashboard_controller.dart';

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
    _qtyController = TextEditingController(
        text: widget.controller.orderTicketQty.toString());
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
    _syncTextControllers(controller);

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.request_quote_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('KIS Live Manual Order',
                style: Theme.of(context).textTheme.titleMedium),
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

    final qty = controller.orderTicketQty.toString();
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
          decoration: const InputDecoration(
            labelText: 'Qty',
            border: OutlineInputBorder(),
          ),
          keyboardType: TextInputType.number,
          onChanged: (value) =>
              controller.setOrderTicketQty(int.tryParse(value) ?? 1),
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
        onPressed: controller.orderValidationLoading
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
        title: const Text('Confirm real KIS live order'),
        subtitle: const Text(
          'Manual-only lane; scheduler and AI auto trading do not submit KIS orders.',
        ),
      ),
      const SizedBox(height: 8),
      _PreSubmitChecklist(controller: controller),
      const SizedBox(height: 8),
      Wrap(spacing: 8, runSpacing: 8, children: [
        FilledButton.icon(
          onPressed: !controller.canSubmitLiveKisOrder
              ? null
              : () async {
                  final result = await controller.submitKisManualOrder();
                  if (!context.mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                    content: Text(result.message),
                    backgroundColor:
                        result.success ? Colors.green : Colors.redAccent,
                  ));
                },
          icon: controller.kisManualSubmitLoading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2))
              : const Icon(Icons.send_outlined),
          label: Text(controller.kisManualSubmitLoading
              ? 'Submitting...'
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

class _RuntimeSafetyStatusCard extends StatelessWidget {
  const _RuntimeSafetyStatusCard({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final status = controller.kisSafetyStatus;
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
          _DataPair(
              label: 'entry_allowed_now',
              value: status.entryAllowedNow.toString()),
          _DataPair(label: 'no_new_entry_after', value: status.noNewEntryAfter),
        ]),
        const SizedBox(height: 10),
        _StateLine(
          text: controller.kisRuntimeLiveSubmitMessage(),
          color: controller.kisRuntimeLiveSubmitGatesOpen
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
    final qtyMatches = validation?.qty == controller.orderTicketQty;
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
          label: 'market entry allowed', passed: status.entryAllowedNow),
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
          for (final order in history)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: _RecentKisOrderRow(order: order, controller: controller),
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
    return InkWell(
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
                '${order.symbol} ${order.side.toUpperCase()} ${_nullableQuantity(order.requestedQty)}',
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                    color: Colors.white70, fontWeight: FontWeight.w700),
              ),
            ),
            const SizedBox(width: 8),
            _ClearStatusPill(order: order),
          ]),
          const SizedBox(height: 8),
          Wrap(spacing: 12, runSpacing: 8, children: [
            _DataPair(label: 'Order ID', value: order.orderId.toString()),
            _DataPair(label: 'KIS ODNO', value: order.kisOdno ?? 'n/a'),
            _DataPair(label: 'Symbol', value: order.symbol),
            _DataPair(label: 'Side', value: order.side.toUpperCase()),
            _DataPair(
                label: 'Qty', value: _nullableQuantity(order.requestedQty)),
            _DataPair(label: 'internal_status', value: order.internalStatus),
            _DataPair(
                label: 'broker_status',
                value: order.brokerOrderStatus ?? 'n/a'),
            _DataPair(label: 'created_at', value: order.createdAt ?? 'n/a'),
            _DataPair(
                label: 'last_synced_at', value: order.lastSyncedAt ?? 'n/a'),
            _DataPair(label: 'State', value: _syncState(order)),
          ]),
          const SizedBox(height: 8),
          _OrderTimeline(order: order),
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
          if (result.marketSession.noNewEntryAfter?.isNotEmpty == true)
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
