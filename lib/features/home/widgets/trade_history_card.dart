import 'dart:async';

import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/trade_fill_history.dart';
import '../../dashboard/dashboard_controller.dart';

class TradeHistoryCard extends StatefulWidget {
  const TradeHistoryCard({super.key, required this.controller});
  final DashboardController controller;

  @override
  State<TradeHistoryCard> createState() => _TradeHistoryCardState();
}

class _TradeHistoryCardState extends State<TradeHistoryCard>
    with AutomaticKeepAliveClientMixin {
  bool _expanded = false;
  static const _periods = {
    'today': '오늘',
    'week': '1주',
    'month': '1개월',
    'year': '1년'
  };
  @override
  bool get wantKeepAlive => true;

  void _load() => scheduleMicrotask(() {
        if (mounted) unawaited(widget.controller.loadTradeFills());
      });

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant TradeHistoryCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      _expanded = false;
      _load();
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    final controller = widget.controller;
    final page = controller.tradeFillPage;
    final currency = controller.isKisSelected ? 'KRW' : 'USD';
    final period = _periods[controller.tradeFillPeriod]!;
    final hasTrades = page != null && (page.count ?? 0) > 0;
    return SectionCard(
      key: const ValueKey('home-trade-history-card'),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: InkWell(
        onTap: () => setState(() => _expanded = !_expanded),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.center, children: [
            Expanded(
                child: InkWell(
              key: const ValueKey('home-trade-history-toggle'),
              onTap: () => setState(() => _expanded = !_expanded),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 5),
                child: Wrap(
                    spacing: 6,
                    runSpacing: 2,
                    crossAxisAlignment: WrapCrossAlignment.center,
                    children: [
                      const Text('거래 내역',
                          style: TextStyle(
                              fontSize: 18, fontWeight: FontWeight.w800)),
                      if (hasTrades)
                        Text('· $period ${page.count}건',
                            key: const ValueKey('trade-history-count'),
                            style: const TextStyle(
                                fontSize: 20, fontWeight: FontWeight.w900)),
                    ]),
              ),
            )),
            if (page?.environment != null)
              Text(page!.environment == 'live' ? 'LIVE' : 'PAPER',
                  style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                      color: page.environment == 'live'
                          ? AppTheme.danger
                          : Colors.white70)),
            IconButton(
              key: const ValueKey('trade-history-refresh'),
              tooltip: '거래 내역 새로고침',
              onPressed: controller.tradeFillLoading
                  ? null
                  : () => controller.loadTradeFills(force: true),
              icon: const Icon(Icons.refresh, size: 20),
            ),
            IconButton(
              key: const ValueKey('trade-history-expand'),
              tooltip: _expanded ? '거래 내역 접기' : '거래 내역 펼치기',
              onPressed: () => setState(() => _expanded = !_expanded),
              icon: Icon(_expanded ? Icons.expand_less : Icons.expand_more),
            ),
          ]),
          if (_expanded) ...[
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final entry in _periods.entries)
                ChoiceChip(
                  key: ValueKey('trade-period-${entry.key}'),
                  label: Text(entry.value,
                      style: TextStyle(
                          fontWeight: FontWeight.w800,
                          color: controller.tradeFillPeriod == entry.key
                              ? AppTheme.canvas
                              : Colors.white)),
                  selectedColor: AppTheme.primaryAccent,
                  backgroundColor: AppTheme.surfaceElevated,
                  side: const BorderSide(color: Colors.white38),
                  selected: controller.tradeFillPeriod == entry.key,
                  onSelected: (_) =>
                      controller.loadTradeFills(period: entry.key),
                ),
            ]),
            const SizedBox(height: 6),
            Text(
                controller.isKisSelected
                    ? '한국투자증권 계좌 체결 · KST'
                    : '확인된 거래 · KST',
                style: const TextStyle(fontSize: 12, color: Colors.white70)),
          ],
          if (controller.tradeFillLoading) ...[
            const SizedBox(height: 6),
            Text(controller.isKisSelected ? 'KIS 거래 내역 조회 중' : '거래 내역 조회 중',
                style: const TextStyle(fontWeight: FontWeight.w600)),
            const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: LinearProgressIndicator(
                    key: ValueKey('trade-history-loading'))),
          ] else if (controller.tradeFillError != null) ...[
            Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 8,
                children: [
                  Text(controller.tradeFillError!,
                      style: const TextStyle(
                          color: AppTheme.warning,
                          fontWeight: FontWeight.w600)),
                  TextButton(
                      key: const ValueKey('trade-history-retry'),
                      onPressed: () => controller.loadTradeFills(force: true),
                      child: const Text('다시 시도')),
                ]),
            if (controller.tradeFillErrorCode == 'historical_query_after_close')
              const Text('과거 체결 내역은 15:30 이후 다시 조회해 주세요.',
                  style: TextStyle(fontSize: 12, color: Colors.white70)),
          ] else if (page != null) ...[
            if (!hasTrades) ...[
              Text('$period 체결 0건',
                  style: const TextStyle(
                      fontSize: 17, fontWeight: FontWeight.w800)),
              if (_expanded)
                const Text('선택한 기간에 실제 체결 내역이 없습니다.',
                    style: TextStyle(color: Colors.white70)),
            ] else ...[
              Wrap(spacing: 18, runSpacing: 4, children: [
                Text('매수 ${_money(currency, page.buyAmount)}',
                    key: const ValueKey('trade-history-buy-total'),
                    style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: AppTheme.danger)),
                Text('매도 ${_money(currency, page.sellAmount)}',
                    style: const TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w800,
                        color: AppTheme.primaryAccent)),
              ]),
              if (page.unknownAmountCount > 0)
                Text('금액 미확인 ${page.unknownAmountCount}건',
                    style: const TextStyle(color: Colors.white70)),
              for (final fill in _expanded
                  ? controller.tradeFills
                  : controller.tradeFills.take(1))
                _FillRow(fill: fill, expanded: _expanded),
              if (_expanded && page.nextOffset != null)
                TextButton(
                    key: const ValueKey('trade-history-more'),
                    onPressed: controller.tradeFillLoadingMore
                        ? null
                        : () => controller.loadTradeFills(more: true),
                    child: Text(
                        controller.tradeFillLoadingMore ? '불러오는 중…' : '더 보기')),
            ],
          ],
        ]),
      ),
    );
  }
}

class _FillRow extends StatelessWidget {
  const _FillRow({required this.fill, required this.expanded});
  final TradeFill fill;
  final bool expanded;

  @override
  Widget build(BuildContext context) {
    final side = fill.side == 'buy' ? '매수' : '매도';
    final color = fill.side == 'buy' ? AppTheme.danger : AppTheme.primaryAccent;
    final title =
        fill.name.isEmpty ? fill.symbol : '${fill.name} (${fill.symbol})';
    final quantity = NumberFormat('0.#########').format(fill.quantity);
    final kst = fill.filledAt?.toUtc().add(const Duration(hours: 9));
    final date = kst == null
        ? '${fill.tradeDate} · 체결 시각 미확인'
        : '${DateFormat('yyyy-MM-dd HH:mm:ss').format(kst)} KST';
    return Padding(
      key: ValueKey('trade-fill-${fill.id}'),
      padding: const EdgeInsets.only(top: 6),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Text(
            '$side · $title · $quantity주 · ${_money(fill.currency, fill.averagePrice)}'
            '${fill.partial ? ' · 부분 체결' : ''}',
            style: TextStyle(
                fontSize: 16,
                height: 1.4,
                fontWeight: FontWeight.w700,
                color: color)),
        if (expanded) ...[
          Text('체결 금액 ${_money(fill.currency, fill.amount)}',
              style:
                  const TextStyle(fontSize: 15, fontWeight: FontWeight.w700)),
          Text(date,
              style: const TextStyle(fontSize: 12, color: Colors.white70)),
        ],
      ]),
    );
  }
}

String _money(String currency, double? value) => value == null
    ? '미확인'
    : NumberFormat.currency(
            locale: currency == 'KRW' ? 'ko_KR' : 'en_US',
            symbol: currency == 'KRW' ? '₩' : r'$',
            decimalDigits: currency == 'KRW' ? 0 : 2)
        .format(value);
