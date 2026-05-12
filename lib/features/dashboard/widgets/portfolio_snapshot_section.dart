import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/portfolio_summary.dart';
import '../../dashboard/dashboard_controller.dart';

class PortfolioSnapshotSection extends StatelessWidget {
  const PortfolioSnapshotSection({super.key, required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final summary = controller.selectedPortfolioSummary;
    final selectedMarket = controller.selectedPortfolioMarket;
    final isKr = selectedMarket == PortfolioMarket.kr;
    final marketTitle =
        isKr ? 'KR Portfolio / KIS Read-only' : 'US Portfolio / Alpaca Paper';
    final noPositionsText =
        isKr ? 'No open KR positions' : 'No open US positions';
    final noOrdersText = isKr ? 'No pending KR orders' : 'No pending US orders';
    final plColor = _valueColor(summary.totalUnrealizedPl);

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.account_balance_wallet_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Portfolio Snapshot',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          _CountPill(
              text:
                  '${summary.positionsCount} held / ${summary.pendingOrdersCount} pending'),
        ]),
        const SizedBox(height: 12),
        SegmentedButton<PortfolioMarket>(
          segments: const [
            ButtonSegment(
                value: PortfolioMarket.us,
                label: Text('US / Alpaca'),
                icon: Icon(Icons.public, size: 16)),
            ButtonSegment(
                value: PortfolioMarket.kr,
                label: Text('KR / KIS'),
                icon: Icon(Icons.account_balance, size: 16)),
          ],
          selected: {selectedMarket},
          onSelectionChanged: (selection) =>
              controller.selectPortfolioMarket(selection.first),
        ),
        const SizedBox(height: 10),
        Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(marketTitle,
                  style: const TextStyle(
                      color: Colors.white70, fontWeight: FontWeight.w800)),
              if (isKr) ...[
                const _SoftBadge(
                    text: 'READ-ONLY', color: Colors.lightBlueAccent),
                const _SoftBadge(
                    text: 'TRADING DISABLED', color: Colors.amberAccent),
              ],
            ]),
        if (controller.selectedPortfolioUnavailable) ...[
          const SizedBox(height: 10),
          const _EmptyLine(text: 'KIS account data unavailable'),
        ],
        const SizedBox(height: 14),
        LayoutBuilder(builder: (context, constraints) {
          final tileWidth = _metricTileWidth(constraints.maxWidth);
          return Wrap(spacing: 8, runSpacing: 8, children: [
            _MetricTile(
                width: tileWidth,
                label: 'Total Market Value',
                value: _money(summary.totalMarketValue,
                    currency: summary.currency),
                color: Colors.white),
            _MetricTile(
                width: tileWidth,
                label: 'Total Cost',
                value:
                    _money(summary.totalCostBasis, currency: summary.currency),
                color: Colors.white70),
            _MetricTile(
                width: tileWidth,
                label: 'Unrealized P/L',
                value: _money(summary.totalUnrealizedPl,
                    currency: summary.currency, signed: true),
                color: plColor),
            _MetricTile(
                width: tileWidth,
                label: 'Profit %',
                value: _percentOrDash(
                    _portfolioProfitPercent(summary, isKr: isKr),
                    signed: true),
                color: plColor),
            _MetricTile(
                width: tileWidth,
                label: isKr ? 'Available Cash' : 'Cash',
                value: _money(summary.cash, currency: summary.currency),
                color: Colors.white70),
          ]);
        }),
        const SizedBox(height: 16),
        const _SubsectionTitle('Current Holdings'),
        const SizedBox(height: 8),
        if (summary.positions.isEmpty)
          _EmptyLine(text: noPositionsText)
        else
          Column(children: [
            for (final position in summary.positions) ...[
              _PositionTile(
                  position: position, currency: summary.currency, isKr: isKr),
              if (position != summary.positions.last) const SizedBox(height: 8),
            ],
          ]),
        const SizedBox(height: 16),
        const _SubsectionTitle('Pending Orders'),
        const SizedBox(height: 8),
        if (summary.pendingOrders.isEmpty)
          _EmptyLine(text: noOrdersText)
        else
          Column(children: [
            for (final order in summary.pendingOrders) ...[
              _PendingOrderTile(order: order, currency: summary.currency),
              if (order != summary.pendingOrders.last)
                const SizedBox(height: 8),
            ],
          ]),
      ]),
    );
  }

  double _metricTileWidth(double maxWidth) {
    if (maxWidth < 420) return maxWidth;
    if (maxWidth < 760) return math.max(0, (maxWidth - 8) / 2);
    return math.max(0, (maxWidth - 32) / 5);
  }
}

class _MetricTile extends StatelessWidget {
  const _MetricTile({
    required this.width,
    required this.label,
    required this.value,
    required this.color,
  });

  final double width;
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: width,
      height: 74,
      child: Container(
        padding: const EdgeInsets.all(10),
        decoration: BoxDecoration(
          color: Colors.white.withValues(alpha: 0.05),
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(label.toUpperCase(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                  color: Colors.white60,
                  fontSize: 10,
                  fontWeight: FontWeight.w700)),
          const Spacer(),
          FittedBox(
            alignment: Alignment.centerLeft,
            fit: BoxFit.scaleDown,
            child: Text(value,
                style: TextStyle(
                    color: color, fontSize: 17, fontWeight: FontWeight.w800)),
          ),
        ]),
      ),
    );
  }
}

class _PositionTile extends StatelessWidget {
  const _PositionTile({
    required this.position,
    required this.currency,
    required this.isKr,
  });

  final PositionSummary position;
  final String currency;
  final bool isKr;

  @override
  Widget build(BuildContext context) {
    final plColor = _valueColor(position.unrealizedPl);

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
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(position.symbol,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w800)),
              if (position.name.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(position.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white60,
                        fontSize: 12,
                        fontWeight: FontWeight.w600)),
              ],
            ]),
          ),
          const SizedBox(width: 8),
          _SoftBadge(text: position.side.toUpperCase(), color: Colors.white70),
          const SizedBox(width: 8),
          Text('Qty ${_quantity(position.qty)}',
              style: const TextStyle(
                  color: Colors.white70, fontWeight: FontWeight.w700)),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(
              label: 'Avg Buy / Share',
              value: _money(position.avgEntryPrice, currency: currency)),
          _DataPair(
              label: 'Current / Share',
              value: position.currentPrice == null
                  ? 'n/a'
                  : _money(position.currentPrice!, currency: currency)),
          _DataPair(
              label: 'Cost',
              value: _money(position.costBasis, currency: currency)),
          _DataPair(
              label: 'Current Value',
              value: _money(position.marketValue, currency: currency)),
          _DataPair(
              label: 'P/L',
              value: _money(position.unrealizedPl,
                  currency: currency, signed: true),
              color: plColor),
          _DataPair(
              label: 'Profit',
              value: _percentOrDash(
                  _positionProfitPercent(position, isKr: isKr),
                  signed: true),
              color: plColor),
        ]),
      ]),
    );
  }
}

class _PendingOrderTile extends StatelessWidget {
  const _PendingOrderTile({required this.order, required this.currency});

  final PendingOrderSummary order;
  final String currency;

  @override
  Widget build(BuildContext context) {
    final side = order.side.toUpperCase();
    final sideColor =
        side == 'BUY' ? Colors.greenAccent : Colors.deepOrangeAccent;

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
          _SoftBadge(text: side.isEmpty ? 'ORDER' : side, color: sideColor),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(order.symbol,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w800)),
              if (order.name.isNotEmpty) ...[
                const SizedBox(height: 2),
                Text(order.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                        color: Colors.white60,
                        fontSize: 12,
                        fontWeight: FontWeight.w600)),
              ],
            ]),
          ),
          Text(_cleanStatus(order.status),
              style: const TextStyle(
                  color: Colors.white70, fontWeight: FontWeight.w700)),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 14, runSpacing: 8, children: [
          _DataPair(label: 'Quantity', value: _orderQuantity(order)),
          if (order.unfilledQty != null)
            _DataPair(label: 'Unfilled', value: _quantity(order.unfilledQty!)),
          if (order.price != null)
            _DataPair(
                label: 'Price',
                value: _money(order.price!, currency: currency)),
          _DataPair(
              label: 'Estimated Amount',
              value: order.estimatedAmount == null
                  ? 'n/a'
                  : _money(order.estimatedAmount!, currency: currency)),
          if (order.type.isNotEmpty)
            _DataPair(label: 'Type', value: _cleanStatus(order.type)),
          if (order.submittedAt != null)
            _DataPair(label: 'Submitted', value: order.submittedAt!),
        ]),
      ]),
    );
  }

  String _orderQuantity(PendingOrderSummary order) {
    if (order.qty != null) return _quantity(order.qty!);
    if (order.notional != null) {
      return _money(order.notional!, currency: currency);
    }
    return 'n/a';
  }
}

class _DataPair extends StatelessWidget {
  const _DataPair({required this.label, required this.value, this.color});

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return ConstrainedBox(
      constraints: const BoxConstraints(minWidth: 108, maxWidth: 180),
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
            style: TextStyle(
                color: color ?? Colors.white,
                fontSize: 13,
                fontWeight: FontWeight.w700)),
      ]),
    );
  }
}

class _SubsectionTitle extends StatelessWidget {
  const _SubsectionTitle(this.text);

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text,
        style: const TextStyle(
            color: Colors.white70, fontWeight: FontWeight.w800));
  }
}

class _EmptyLine extends StatelessWidget {
  const _EmptyLine({required this.text});

  final String text;

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
      child: Text(text, style: const TextStyle(color: Colors.white60)),
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

class _CountPill extends StatelessWidget {
  const _CountPill({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.07),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Text(text,
          style: const TextStyle(
              color: Colors.white70,
              fontSize: 11,
              fontWeight: FontWeight.w700)),
    );
  }
}

Color _valueColor(double value) {
  if (value > 0) return Colors.greenAccent;
  if (value < 0) return Colors.redAccent;
  return Colors.white70;
}

String _money(double value, {required String currency, bool signed = false}) {
  final normalizedCurrency = currency.toUpperCase();
  final decimals = normalizedCurrency == 'KRW' ? 0 : 2;
  final formatted = _groupedNumber(value.abs(), decimals: decimals);
  final symbol = normalizedCurrency == 'KRW' ? '₩' : r'$';
  final prefix = signed
      ? value > 0
          ? '+'
          : value < 0
              ? '-'
              : ''
      : value < 0
          ? '-'
          : '';
  if (normalizedCurrency == 'KRW') {
    return '$prefix$symbol$formatted';
  }
  return '$prefix$symbol$formatted';
}

String _groupedNumber(double value, {required int decimals}) {
  final fixed = value.toStringAsFixed(decimals);
  final parts = fixed.split('.');
  final whole = parts.first;
  final buffer = StringBuffer();
  for (var i = 0; i < whole.length; i += 1) {
    final remaining = whole.length - i;
    buffer.write(whole[i]);
    if (remaining > 1 && remaining % 3 == 1) {
      buffer.write(',');
    }
  }
  if (decimals == 0) return buffer.toString();
  return '${buffer.toString()}.${parts.last}';
}

String _percent(double value, {bool signed = false}) {
  final prefix = signed
      ? value > 0
          ? '+'
          : value < 0
              ? '-'
              : ''
      : value < 0
          ? '-'
          : '';
  return '$prefix${(value.abs() * 100).toStringAsFixed(2)}%';
}

String _percentOrDash(double? value, {bool signed = false}) {
  if (value == null) return '--';
  return _percent(value, signed: signed);
}

double? _portfolioProfitPercent(
  PortfolioSummary summary, {
  required bool isKr,
}) {
  if (!isKr) return summary.totalUnrealizedPlpc;
  if (summary.totalCostBasis <= 0) return null;
  final unrealizedPl = summary.totalUnrealizedPl != 0
      ? summary.totalUnrealizedPl
      : summary.totalMarketValue - summary.totalCostBasis;
  return unrealizedPl / summary.totalCostBasis;
}

double? _positionProfitPercent(
  PositionSummary position, {
  required bool isKr,
}) {
  if (!isKr) return position.unrealizedPlpc;
  if (position.costBasis <= 0) return null;
  final unrealizedPl = position.unrealizedPl != 0
      ? position.unrealizedPl
      : position.marketValue - position.costBasis;
  return unrealizedPl / position.costBasis;
}

String _quantity(double value) {
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value
      .toStringAsFixed(6)
      .replaceFirst(RegExp(r'0+$'), '')
      .replaceFirst(RegExp(r'\.$'), '');
}

String _cleanStatus(String value) {
  if (value.isEmpty) return 'n/a';
  return value.replaceAll('_', ' ').toUpperCase();
}
