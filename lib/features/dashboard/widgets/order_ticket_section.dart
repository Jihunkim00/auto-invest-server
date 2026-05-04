import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/order_validation_result.dart';
import '../../dashboard/dashboard_controller.dart';

class OrderTicketSection extends StatefulWidget {
  const OrderTicketSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  State<OrderTicketSection> createState() => _OrderTicketSectionState();
}

class _OrderTicketSectionState extends State<OrderTicketSection> {
  late final TextEditingController _symbolController;
  late final TextEditingController _qtyController;

  @override
  void initState() {
    super.initState();
    _symbolController =
        TextEditingController(text: widget.controller.orderTicketSymbol);
    _qtyController = TextEditingController(
        text: widget.controller.orderTicketQty.toString());
  }

  @override
  void dispose() {
    _symbolController.dispose();
    _qtyController.dispose();
    super.dispose();
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
            child: Text('Order Ticket',
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
    final realOrdersAllowed = controller.schedulerStatus.kr.realOrdersAllowed;

    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 8, runSpacing: 8, children: const [
        _SoftBadge(text: 'DRY-RUN ONLY', color: Colors.lightBlueAccent),
        _SoftBadge(text: 'TRADING DISABLED', color: Colors.amberAccent),
      ]),
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
      OutlinedButton.icon(
        onPressed: null,
        icon: const Icon(Icons.lock_outline),
        label: const Text('Submit Real KIS Order — coming after validation UI wiring'),
      ),
      const SizedBox(height: 10),
      _StateLine(
        text: realOrdersAllowed
            ? 'Real KIS trading requires manual backend confirmation'
            : 'Real KIS trading is disabled',
        color: realOrdersAllowed ? Colors.amberAccent : Colors.redAccent,
      ),
      const SizedBox(height: 8),
      const _StateLine(text: 'Use dry-run validation first'),
      const SizedBox(height: 12),
      if (controller.orderValidationError != null)
        _StateLine(
          text: controller.orderValidationError!,
          color: Colors.redAccent,
        ),
      if (controller.orderValidationResult != null)
        _ValidationResultCard(result: controller.orderValidationResult!),
    ]);
  }
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
        if (result.warnings.isNotEmpty) ...[
          const SizedBox(height: 12),
          _ReasonList(title: 'Warnings', items: result.warnings),
        ],
        if (result.blockReasons.isNotEmpty) ...[
          const SizedBox(height: 12),
          _ReasonList(title: 'Block Reasons', items: result.blockReasons),
        ],
        const SizedBox(height: 12),
        _StateLine(
            text:
                'Payload preview: ${result.orderPreview.payloadPreview.toString()}'),
      ]),
    );
  }
}

class _ReasonList extends StatelessWidget {
  const _ReasonList({required this.title, required this.items});

  final String title;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Text(title.toUpperCase(),
          style: const TextStyle(
              color: Colors.white54,
              fontSize: 10,
              fontWeight: FontWeight.w800)),
      const SizedBox(height: 4),
      for (final item in items)
        Text(item,
            style: const TextStyle(
                color: Colors.white70, fontWeight: FontWeight.w700)),
    ]);
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
