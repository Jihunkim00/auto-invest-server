import 'dart:convert';
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/portfolio_summary.dart';
import '../../../models/managed_position.dart';
import '../../dashboard/dashboard_controller.dart';

class PortfolioSnapshotSection extends StatelessWidget {
  const PortfolioSnapshotSection({
    super.key,
    required this.controller,
    this.managementMode = false,
    this.onOpenManualOrder,
    this.onReviewPosition,
  });

  final DashboardController controller;
  final bool managementMode;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;

  @override
  Widget build(BuildContext context) {
    final summary = controller.selectedPortfolioSummary;
    final selectedMarket = controller.selectedPortfolioMarket;
    final isKr = selectedMarket == PortfolioMarket.kr;
    final marketTitle =
        isKr ? 'KR Portfolio / KIS Read-only' : 'US Portfolio / Alpaca Paper';
    final noPositionsText = isKr && summary.positionsUnavailable
        ? 'KIS positions unavailable'
        : isKr
            ? 'No open KR positions'
            : 'No open US positions';
    final noOrdersText = isKr && summary.openOrdersUnavailable
        ? 'KIS open orders unavailable'
        : isKr
            ? 'No pending KR orders'
            : 'No pending US orders';
    final plColor = _valueColor(summary.totalUnrealizedPl);
    final countText = isKr && summary.hasUnavailableKisData
        ? '${summary.positionsUnavailable ? '--' : summary.positionsCount} held / ${summary.openOrdersUnavailable ? '--' : summary.pendingOrdersCount} pending'
        : '${summary.positionsCount} held / ${summary.pendingOrdersCount} pending';

    return SectionCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(children: [
          const Icon(Icons.account_balance_wallet_outlined, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text('Portfolio Snapshot',
                style: Theme.of(context).textTheme.titleMedium),
          ),
          _CountPill(text: countText),
        ]),
        const SizedBox(height: 12),
        Wrap(
            spacing: 8,
            runSpacing: 8,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(marketTitle,
                  style: const TextStyle(
                      color: Colors.white70, fontWeight: FontWeight.w800)),
              _SoftBadge(
                text: isKr ? 'GLOBAL: KIS / KR' : 'GLOBAL: ALPACA / US',
                color: isKr ? Colors.redAccent : Colors.lightBlueAccent,
              ),
              if (isKr) ...[
                const _SoftBadge(
                    text: 'READ-ONLY', color: Colors.lightBlueAccent),
                const _SoftBadge(
                    text: 'TRADING DISABLED', color: Colors.amberAccent),
              ],
            ]),
        if (isKr && summary.tokenExpired) ...[
          const SizedBox(height: 10),
          _WarningNote(
            text: summary.kisAuthErrorMessage ??
                'KIS token expired. Portfolio data is unavailable until token refresh succeeds.',
            detail: summary.nextRefreshAllowedAt == null
                ? null
                : 'Token refresh is temporarily blocked until ${summary.nextRefreshAllowedAt}.',
          ),
        ] else if (controller.selectedPortfolioUnavailable) ...[
          const SizedBox(height: 10),
          _EmptyLine(
              text: controller.krPortfolioError ??
                  'KIS account data unavailable'),
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
                value: isKr && !summary.cashKnown
                    ? 'Unavailable'
                    : _money(summary.cash, currency: summary.currency),
                color: Colors.white70),
          ]);
        }),
        const SizedBox(height: 16),
        const _SubsectionTitle('Current Holdings'),
        if (isKr && controller.kisManagedPositionsLoading) ...[
          const SizedBox(height: 6),
          const _StateNote(text: 'Loading KIS position management...'),
        ],
        if (isKr && controller.kisManagedPositionsError != null) ...[
          const SizedBox(height: 6),
          _StateNote(text: controller.kisManagedPositionsError!),
        ],
        const SizedBox(height: 8),
        if (summary.positions.isEmpty)
          _EmptyLine(text: noPositionsText)
        else
          Column(children: [
            for (final position in summary.positions) ...[
              _PositionTile(
                controller: controller,
                position: position,
                managedPosition: isKr
                    ? controller.kisManagedPositionForSymbol(position.symbol)
                    : null,
                currency: summary.currency,
                isKr: isKr,
                managementMode: managementMode,
                onOpenManualOrder: onOpenManualOrder,
                onReviewPosition: onReviewPosition,
              ),
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
    required this.controller,
    required this.position,
    this.managedPosition,
    required this.currency,
    required this.isKr,
    required this.managementMode,
    this.onOpenManualOrder,
    this.onReviewPosition,
  });

  final DashboardController controller;
  final PositionSummary position;
  final ManagedPosition? managedPosition;
  final String currency;
  final bool isKr;
  final bool managementMode;
  final VoidCallback? onOpenManualOrder;
  final VoidCallback? onReviewPosition;

  @override
  Widget build(BuildContext context) {
    final unrealizedPl = managedPosition?.unrealizedPl ?? position.unrealizedPl;
    final plColor = _valueColor(unrealizedPl);
    final status =
        managedPosition?.statusLabel ?? _positionStatus(position, isKr: isKr);
    final reason = managedPosition?.humanReason ??
        _positionStatusReason(position, isKr: isKr);
    final company = _companyLabel(position, managedPosition);
    final canPrepareManualSell = isKr &&
        managementMode &&
        managedPosition != null &&
        !managedPosition!.isHold &&
        managedPosition!.canPrepareManualSell;

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          key: ValueKey('portfolio-position-card-${position.symbol}'),
          tilePadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
          childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          title: Row(children: [
            Expanded(
              child: Text('${position.symbol} · $company',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                      fontSize: 16, fontWeight: FontWeight.w800)),
            ),
            const SizedBox(width: 8),
            _SoftBadge(text: status, color: _positionStatusColor(status)),
          ]),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Wrap(spacing: 8, runSpacing: 6, children: [
              _SoftBadge(
                  text: position.side.toUpperCase(), color: Colors.white70),
              _SoftBadge(
                  text: 'Qty ${_quantity(position.qty)}',
                  color: Colors.white70),
              _DataPair(
                  label: 'Current Value',
                  value: _money(
                      managedPosition?.currentValue ?? position.marketValue,
                      currency: currency)),
              _DataPair(
                  label: 'P/L',
                  value: _money(unrealizedPl, currency: currency, signed: true),
                  color: plColor),
              _DataPair(
                  label: 'Profit',
                  value: _percentOrDash(
                      managedPosition?.unrealizedPlPct ??
                          _positionProfitPercent(position, isKr: isKr),
                      signed: true),
                  color: plColor),
              _DataPair(label: 'Main reason', value: reason),
            ]),
          ),
          children: [
            _PositionDetail(
              position: position,
              managedPosition: managedPosition,
              currency: currency,
              isKr: isKr,
            ),
            if (managementMode) ...[
              const SizedBox(height: 12),
              Wrap(spacing: 8, runSpacing: 8, children: [
                OutlinedButton.icon(
                  onPressed: onReviewPosition,
                  icon: const Icon(Icons.rate_review_outlined, size: 18),
                  label: const Text('Review'),
                ),
                if (canPrepareManualSell)
                  OutlinedButton.icon(
                    key: ValueKey('prepare-manual-sell-${position.symbol}'),
                    onPressed: () async {
                      final result = await controller
                          .prepareKisManualSellFromManagedPosition(
                              managedPosition!);
                      if (result.success) onOpenManualOrder?.call();
                      if (!context.mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
                    icon: const Icon(Icons.request_quote_outlined, size: 18),
                    label: const Text('Prepare Manual Sell'),
                  )
                else if (isKr && managementMode && managedPosition == null)
                  OutlinedButton.icon(
                    onPressed: () {
                      final result =
                          controller.prepareKisManualSellFromPosition(position);
                      if (result.success) onOpenManualOrder?.call();
                      ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                        content: Text(result.message),
                        backgroundColor:
                            result.success ? Colors.green : Colors.redAccent,
                      ));
                    },
                    icon: const Icon(Icons.request_quote_outlined, size: 18),
                    label: const Text('Prepare Manual Sell'),
                  ),
              ]),
            ],
          ],
        ),
      ),
    );
  }
}

class _PositionDetail extends StatelessWidget {
  const _PositionDetail({
    required this.position,
    required this.managedPosition,
    required this.currency,
    required this.isKr,
  });

  final PositionSummary position;
  final ManagedPosition? managedPosition;
  final String currency;
  final bool isKr;

  @override
  Widget build(BuildContext context) {
    final managed = managedPosition;
    final technical = managed?.technicalSnapshot ?? const <String, dynamic>{};
    final flags = managed == null
        ? const <String>[]
        : [
            if (managed.stopLossTriggered) 'Stop loss',
            if (managed.takeProfitTriggered) 'Take profit',
            if (managed.weakTrendTriggered) 'Weak trend',
            if (managed.sellPressureTriggered) 'Sell pressure',
            if (managed.manualReviewRequired) 'Manual review',
          ];
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      Wrap(spacing: 14, runSpacing: 8, children: [
        _DataPair(
            label: 'Avg Buy / Share',
            value: _money(managed?.averagePrice ?? position.avgEntryPrice,
                currency: currency)),
        _DataPair(
            label: 'Current / Share',
            value: _nullableMoney(
                managed?.currentPrice ?? position.currentPrice,
                currency: currency)),
        _DataPair(
            label: 'Cost',
            value: _nullableMoney(managed?.costBasis ?? position.costBasis,
                currency: currency)),
        _DataPair(
            label: 'Current Value',
            value: _nullableMoney(managed?.currentValue ?? position.marketValue,
                currency: currency)),
        _DataPair(
            label: 'P/L',
            value: _nullableMoney(
                managed?.unrealizedPl ?? position.unrealizedPl,
                currency: currency,
                signed: true),
            color: _valueColor(managed?.unrealizedPl ?? position.unrealizedPl)),
        _DataPair(
            label: 'Profit',
            value: _percentOrDash(
                managed?.unrealizedPlPct ??
                    _positionProfitPercent(position, isKr: isKr),
                signed: true),
            color: _valueColor(managed?.unrealizedPl ?? position.unrealizedPl)),
        _DataPair(
            label: 'Sell Score', value: _numberOrDash(managed?.finalSellScore)),
        _DataPair(
            label: 'Buy Score', value: _numberOrDash(managed?.finalBuyScore)),
        _DataPair(
            label: 'Quant Sell', value: _numberOrDash(managed?.quantSellScore)),
        _DataPair(
            label: 'Quant Buy', value: _numberOrDash(managed?.quantBuyScore)),
        _DataPair(label: 'AI Sell', value: _numberOrDash(managed?.aiSellScore)),
        _DataPair(label: 'AI Buy', value: _numberOrDash(managed?.aiBuyScore)),
        _DataPair(
            label: 'Confidence',
            value: managed?.confidence == null
                ? 'n/a'
                : _percent(managed!.confidence!)),
        _DataPair(
            label: 'Indicator',
            value: _technicalText(technical, 'indicator_status')),
        _DataPair(
            label: 'Bars',
            value: _technicalText(technical, 'indicator_bar_count')),
      ]),
      const SizedBox(height: 12),
      const _SubsectionTitle('Technical Snapshot'),
      const SizedBox(height: 8),
      Wrap(spacing: 14, runSpacing: 8, children: [
        _DataPair(
            label: 'EMA20',
            value:
                '${_technicalNumber(technical, 'ema20')} (${_technicalText(technical, 'price_vs_ema20')})'),
        _DataPair(
            label: 'EMA50',
            value:
                '${_technicalNumber(technical, 'ema50')} (${_technicalText(technical, 'price_vs_ema50')})'),
        _DataPair(
            label: 'VWAP',
            value:
                '${_technicalNumber(technical, 'vwap')} (${_technicalText(technical, 'price_vs_vwap')})'),
        _DataPair(label: 'RSI', value: _technicalNumber(technical, 'rsi')),
        _DataPair(label: 'ATR', value: _technicalNumber(technical, 'atr')),
        _DataPair(
            label: 'Volume ratio',
            value: _technicalNumber(technical, 'volume_ratio')),
        _DataPair(
            label: 'Momentum', value: _technicalPercent(technical, 'momentum')),
        _DataPair(
            label: 'Recent return',
            value: _technicalPercent(technical, 'recent_return')),
      ]),
      const SizedBox(height: 12),
      Wrap(spacing: 8, runSpacing: 8, children: [
        if (flags.isEmpty)
          const _SoftBadge(
              text: 'No exit trigger', color: Colors.lightBlueAccent)
        else
          for (final flag in flags)
            _SoftBadge(text: flag, color: Colors.amberAccent),
        for (final reason in managed?.blockReasons ?? const <String>[])
          _SoftBadge(text: _cleanStatus(reason), color: Colors.redAccent),
      ]),
      if (managed?.latestManualSellOrder != null) ...[
        const SizedBox(height: 12),
        _StateNote(
            text: 'Latest manual sell order is available in KIS Orders.'),
      ],
      if (managed != null) ...[
        const SizedBox(height: 12),
        _DeveloperPayload(payload: managed.rawPayload),
      ],
    ]);
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

class _WarningNote extends StatelessWidget {
  const _WarningNote({required this.text, this.detail});

  final String text;
  final String? detail;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
      decoration: BoxDecoration(
        color: Colors.amberAccent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.amberAccent.withValues(alpha: 0.28)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(text,
            style: const TextStyle(
                color: Colors.amberAccent, fontWeight: FontWeight.w800)),
        if (detail != null) ...[
          const SizedBox(height: 4),
          Text(detail!, style: const TextStyle(color: Colors.white70)),
        ],
      ]),
    );
  }
}

class _StateNote extends StatelessWidget {
  const _StateNote({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Text(text,
        style: const TextStyle(color: Colors.white60, fontSize: 12));
  }
}

class _DeveloperPayload extends StatelessWidget {
  const _DeveloperPayload({required this.payload});

  final Map<String, dynamic> payload;

  @override
  Widget build(BuildContext context) {
    return ExpansionTile(
      tilePadding: EdgeInsets.zero,
      childrenPadding: EdgeInsets.zero,
      title: const Text('Developer Raw Payload',
          style: TextStyle(
              color: Colors.white70,
              fontSize: 12,
              fontWeight: FontWeight.w800)),
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: Colors.black.withValues(alpha: 0.22),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: Colors.white.withValues(alpha: 0.08)),
          ),
          child: SelectableText(
            const JsonEncoder.withIndent('  ').convert(payload),
            style: const TextStyle(
                color: Colors.white70, fontSize: 11, fontFamily: 'monospace'),
          ),
        ),
      ],
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

String _companyLabel(PositionSummary position, ManagedPosition? managed) {
  final value = managed?.companyName ?? position.name;
  if (value.trim().isEmpty) return 'Unknown company';
  return value.trim();
}

Color _valueColor(double value) {
  if (value > 0) return Colors.greenAccent;
  if (value < 0) return Colors.redAccent;
  return Colors.white70;
}

String _nullableMoney(double? value,
    {required String currency, bool signed = false}) {
  if (value == null) return 'n/a';
  return _money(value, currency: currency, signed: signed);
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

String _numberOrDash(double? value) {
  if (value == null) return 'n/a';
  if (value == value.roundToDouble()) return value.toStringAsFixed(0);
  return value.toStringAsFixed(2);
}

String _technicalText(Map<String, dynamic> payload, String key) {
  final value = payload[key];
  if (value == null || value.toString().trim().isEmpty) return 'n/a';
  return value.toString();
}

String _technicalNumber(Map<String, dynamic> payload, String key) {
  final value = _asNullableDouble(payload[key]);
  return _numberOrDash(value);
}

String _technicalPercent(Map<String, dynamic> payload, String key) {
  final value = _asNullableDouble(payload[key]);
  return value == null ? 'n/a' : _percent(value, signed: true);
}

double? _asNullableDouble(Object? value) {
  if (value == null) return null;
  if (value is num) return value.toDouble();
  final text = value.toString().trim().replaceAll(',', '');
  if (text.isEmpty) return null;
  return double.tryParse(text);
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

String _positionStatus(PositionSummary position, {required bool isKr}) {
  final profit = _positionProfitPercent(position, isKr: isKr);
  if (profit == null) return 'REVIEW SELL';
  if (profit <= -0.07) return 'SELL READY';
  if (profit <= -0.03) return 'REVIEW SELL';
  if (profit >= 0.10) return 'SELL READY';
  return 'HOLD';
}

String _positionStatusReason(PositionSummary position, {required bool isKr}) {
  final profit = _positionProfitPercent(position, isKr: isKr);
  if (profit == null) return 'No reliable P/L percentage available.';
  if (profit <= -0.07) return 'Loss is near the stop-loss review band.';
  if (profit <= -0.03) return 'Position is down enough to review.';
  if (profit >= 0.10) return 'Profit is high enough to review taking gains.';
  return 'No sell review trigger from the portfolio view.';
}

Color _positionStatusColor(String status) {
  switch (status) {
    case 'SELL READY':
      return Colors.redAccent;
    case 'REVIEW SELL':
      return Colors.amberAccent;
    default:
      return Colors.lightBlueAccent;
  }
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
