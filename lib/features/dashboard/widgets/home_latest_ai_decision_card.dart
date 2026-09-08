import 'package:flutter/material.dart';

import '../../../core/utils/kr_stock_catalog.dart';
import '../../../core/utils/kr_symbol.dart';
import '../../../core/utils/timestamp_formatter.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/candidate.dart';
import '../../../models/log_items.dart';
import '../../../models/watchlist_run_result.dart';
import '../dashboard_controller.dart';

class HomeLatestAiDecisionCard extends StatelessWidget {
  const HomeLatestAiDecisionCard({
    super.key,
    required this.controller,
    this.nowKst,
  });

  final DashboardController controller;
  final DateTime Function()? nowKst;

  @override
  Widget build(BuildContext context) {
    final candidates = _latestCandidates(controller);
    final candidate = candidates.isEmpty ? null : candidates.first;
    final symbol = candidate?.symbol.isNotEmpty == true
        ? candidate!.symbol
        : (controller.runResult.triggeredSymbol ??
            controller.runResult.finalBestCandidate);
    final display = _displaySymbol(controller, symbol, candidate?.name);
    final score = _scoreLine(candidate, controller.runResult);
    final reason = _shortReason(candidate, controller.runResult);
    final time = _latestTime(controller);

    return Semantics(
      button: true,
      label: '최신 AI 판단 상세 보기',
      child: Align(
        alignment: Alignment.topLeft,
        heightFactor: 1,
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(12),
          child: InkWell(
            key: const ValueKey('home-latest-ai-decision-card'),
            mouseCursor: SystemMouseCursors.click,
            onTap: () => showDialog<void>(
              context: context,
              builder: (_) => _HomeAiDecisionDialog(
                controller: controller,
                nowKst: nowKst,
              ),
            ),
            borderRadius: BorderRadius.circular(12),
            child: SectionCard(
              key: const ValueKey('home-latest-ai-decision-card-surface'),
              padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Icon(Icons.auto_awesome_outlined, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Expanded(
                              child: Text(
                                '최신 AI 판단',
                                style: TextStyle(fontWeight: FontWeight.w800),
                              ),
                            ),
                            if (time != null)
                              Text(time,
                                  style:
                                      const TextStyle(color: Colors.white60)),
                          ],
                        ),
                        const SizedBox(height: 5),
                        Text(
                          display,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(fontWeight: FontWeight.w800),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          score,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: Colors.white70, fontSize: 12),
                        ),
                        const SizedBox(height: 3),
                        Text(
                          reason,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                              color: Colors.white60, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 6),
                  const Padding(
                    padding: EdgeInsets.only(top: 22),
                    child: Icon(Icons.chevron_right, color: Colors.white60),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeAiDecisionDialog extends StatefulWidget {
  const _HomeAiDecisionDialog({required this.controller, this.nowKst});

  final DashboardController controller;
  final DateTime Function()? nowKst;

  @override
  State<_HomeAiDecisionDialog> createState() => _HomeAiDecisionDialogState();
}

class _HomeAiDecisionDialogState extends State<_HomeAiDecisionDialog> {
  int _selectedSlot = 0;

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final slots = _slots(controller);
    final selectedSlotIndex = slots.isEmpty
        ? 0
        : (_selectedSlot >= slots.length ? slots.length - 1 : _selectedSlot);
    final selectedSlot = slots.isEmpty ? null : slots[selectedSlotIndex];
    final candidates = (selectedSlot == null
            ? _latestCandidates(controller)
            : _candidatesForSlot(
                controller,
                selectedSlot,
                nowKst: widget.nowKst,
              ))
        .take(5)
        .toList();
    final blockReason = _blockReasonForSlot(
      controller,
      selectedSlot,
      nowKst: widget.nowKst,
    );
    return AlertDialog(
      key: const ValueKey('home-ai-decision-detail-dialog'),
      title: const Text('오늘의 AI 판단'),
      content: SizedBox(
        width: 680,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (slots.length > 1) ...[
                const Text('분석 슬롯',
                    style: TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  children: [
                    for (var i = 0; i < slots.length; i++)
                      ChoiceChip(
                        key: ValueKey('home-ai-slot-${slots[i]}'),
                        label: Text(slots[i]),
                        selected: selectedSlotIndex == i,
                        onSelected: (_) => setState(() => _selectedSlot = i),
                      ),
                  ],
                ),
                const SizedBox(height: 14),
                const Text(
                  '\uD604\uC7AC API\uAC00 \uC81C\uACF5\uD558\uB294 \uCD5C\uC2E0 \uC2E4\uC81C \uD6C4\uBCF4\uB9CC \uD45C\uC2DC\uD569\uB2C8\uB2E4. \uC2AC\uB86F\uBCC4 \uACB0\uACFC\uAC00 \uC81C\uACF5\uB418\uBA74 \uC120\uD0DD\uD55C \uC2AC\uB86F\uC5D0 \uB9DE\uAC8C \uD45C\uC2DC\uD569\uB2C8\uB2E4.',
                  style: TextStyle(color: Colors.white60, height: 1.35),
                ),
                const SizedBox(height: 8),
                Text('${slots[selectedSlotIndex]} 슬롯의 최신 응답',
                    style: const TextStyle(color: Colors.white70)),
                const SizedBox(height: 10),
              ],
              if (candidates.isEmpty)
                Text(
                  _emptyStateMessage(controller, nowKst: widget.nowKst),
                  key: const ValueKey('home-ai-no-candidates'),
                )
              else
                for (var i = 0; i < candidates.length; i++)
                  _CandidateDetailRow(
                    rank: i + 1,
                    candidate: candidates[i],
                    controller: controller,
                  ),
              if (blockReason.isNotEmpty) ...[
                const SizedBox(height: 12),
                _BlockedReason(
                  reason: blockReason,
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        TextButton(
          key: const ValueKey('home-ai-detail-close'),
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('닫기'),
        ),
      ],
    );
  }
}

class _CandidateDetailRow extends StatelessWidget {
  const _CandidateDetailRow({
    required this.rank,
    required this.candidate,
    required this.controller,
  });

  final int rank;
  final Candidate candidate;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final score = _candidateScoreLine(candidate);
    final reason = _shortCandidateReason(candidate);
    return Container(
      key: ValueKey('home-ai-candidate-$rank'),
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.05),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white12),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '$rank. ${_displaySymbol(controller, candidate.symbol, candidate.name)}',
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 4),
          Text(score, style: const TextStyle(color: Colors.white70)),
          if (reason.isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(reason, style: const TextStyle(color: Colors.white60)),
          ],
          if (candidate.blockReason?.trim().isNotEmpty == true ||
              candidate.blockReasons.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 5),
              child: Text(
                _translateBlockReason(
                  candidate.blockReason ?? candidate.blockReasons.first,
                ),
                style: const TextStyle(color: Colors.orangeAccent),
              ),
            ),
        ],
      ),
    );
  }
}

class _BlockedReason extends StatelessWidget {
  const _BlockedReason({required this.reason});

  final String reason;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey('home-ai-blocked-reason'),
      width: double.infinity,
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: Colors.orangeAccent.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text('차단 사유: ${_translateBlockReason(reason)}'),
    );
  }
}

List<Candidate> _candidates(WatchlistRunResult result) {
  final primary = result.finalRankedCandidates.isNotEmpty
      ? result.finalRankedCandidates
      : result.topQuantCandidates;
  final seen = <String>{};
  return [
    for (final candidate in primary)
      if (candidate.symbol.isNotEmpty && seen.add(candidate.symbol)) candidate,
  ];
}

class _HomeDecisionSnapshot {
  const _HomeDecisionSnapshot({
    required this.atKst,
    required this.candidate,
    required this.reason,
  });

  final DateTime atKst;
  final Candidate candidate;
  final String reason;
}

List<Candidate> _latestCandidates(DashboardController controller) {
  if (controller.showingOfflineFallback) return const [];
  final snapshots = _recentSnapshots(controller)
    ..sort((a, b) => b.atKst.compareTo(a.atKst));
  final recent = _dedupeCandidates(
    snapshots.map((snapshot) => snapshot.candidate),
  );
  if (recent.isNotEmpty) return recent;
  return _candidates(controller.runResult);
}

List<Candidate> _candidatesForSlot(
  DashboardController controller,
  String slot, {
  DateTime Function()? nowKst,
}) {
  if (controller.showingOfflineFallback) return const [];
  final targetMinutes = _slotMinutes(slot);
  if (targetMinutes == null) return _latestCandidates(controller);

  final matches = _matchingSnapshots(
    controller,
    targetMinutes,
    nowKst: nowKst,
  );
  final recent = _dedupeCandidates(
    matches.map((snapshot) => snapshot.candidate),
  );
  if (recent.isNotEmpty) return recent;

  final latestAt = parseTimestampToKst(controller.runResult.createdAt);
  final today = nowKst?.call() ?? currentKst();
  if (latestAt != null &&
      _sameKstDate(latestAt, today) &&
      _withinSlotTolerance(latestAt, targetMinutes)) {
    return _candidates(controller.runResult);
  }

  // Isolated previews and direct run-result views may not have loaded the
  // recent activity list yet. Preserve that already-supported local view.
  if (!controller.homeRecentActivityLoaded) {
    return _candidates(controller.runResult);
  }
  return const [];
}

String _blockReasonForSlot(
  DashboardController controller,
  String? slot, {
  DateTime Function()? nowKst,
}) {
  if (slot != null) {
    final targetMinutes = _slotMinutes(slot);
    if (targetMinutes != null) {
      final matches = _matchingSnapshots(
        controller,
        targetMinutes,
        nowKst: nowKst,
      );
      for (final match in matches) {
        if (match.reason.trim().isNotEmpty) return match.reason.trim();
      }
    }
  }
  return controller.runResult.triggerBlockReason.trim();
}

String _emptyStateMessage(
  DashboardController controller, {
  DateTime Function()? nowKst,
}) {
  if (controller.showingOfflineFallback ||
      controller.homeRecentActivityError != null) {
    return '최근 스케줄러 실행 정보를 불러오지 못했습니다.';
  }
  final today = nowKst?.call() ?? currentKst();
  final hasTodayRun = _recentSnapshots(controller)
          .any((snapshot) => _sameKstDate(snapshot.atKst, today)) ||
      _sameKstDate(
        parseTimestampToKst(controller.runResult.createdAt),
        today,
      );
  if (!hasTodayRun) return '오늘 실행된 스케줄러 분석이 없습니다.';
  return '오늘 실행은 있었지만 이 슬롯에 표시할 후보 데이터가 없습니다.';
}

List<_HomeDecisionSnapshot> _recentSnapshots(
  DashboardController controller,
) {
  final snapshots = <_HomeDecisionSnapshot>[];
  for (final run in controller.automationRecentRuns) {
    if (!_isHomeKisRecord(controller, run.provider, run.market)) continue;
    final atKst = parseTimestampToKst(run.createdAt);
    final candidate = _candidateFromRun(run);
    if (atKst == null || candidate == null) continue;
    snapshots.add(
      _HomeDecisionSnapshot(
        atKst: atKst,
        candidate: candidate,
        reason: run.reason,
      ),
    );
  }
  for (final signal in controller.automationRecentSignals) {
    if (!_isHomeKisRecord(controller, signal.provider, signal.market)) {
      continue;
    }
    final atKst = parseTimestampToKst(signal.createdAt);
    final candidate = _candidateFromSignal(signal);
    if (atKst == null || candidate == null) continue;
    snapshots.add(
      _HomeDecisionSnapshot(
        atKst: atKst,
        candidate: candidate,
        reason: signal.reason,
      ),
    );
  }
  return snapshots;
}

List<_HomeDecisionSnapshot> _matchingSnapshots(
  DashboardController controller,
  int targetMinutes, {
  DateTime Function()? nowKst,
}) {
  final today = nowKst?.call() ?? currentKst();
  final matches = _recentSnapshots(controller)
      .where(
        (snapshot) =>
            _sameKstDate(snapshot.atKst, today) &&
            _withinSlotTolerance(snapshot.atKst, targetMinutes),
      )
      .toList();
  matches.sort((a, b) {
    final distance = _slotDistance(a.atKst, targetMinutes)
        .compareTo(_slotDistance(b.atKst, targetMinutes));
    if (distance != 0) return distance;
    return b.atKst.compareTo(a.atKst);
  });
  return matches;
}

Candidate? _candidateFromRun(TradingLogItem run) {
  final symbol = run.symbol.trim();
  if (symbol.isEmpty || symbol.toUpperCase() == 'UNKNOWN') return null;
  final action = run.action.trim().isEmpty ? 'hold' : run.action.trim();
  return Candidate(
    symbol: symbol,
    score: run.finalBuyScore?.round(),
    note: run.reason,
    entryReady: action.toLowerCase() == 'buy',
    actionHint: action,
    blockReason: null,
    finalBuyScore: run.finalBuyScore,
    finalScore: run.finalBuyScore,
    buyScore: run.finalBuyScore,
    action: action,
    result: run.result,
    status: run.result,
    reason: run.reason,
  );
}

Candidate? _candidateFromSignal(SignalLogItem signal) {
  final symbol = signal.symbol.trim();
  if (symbol.isEmpty || symbol.toUpperCase() == 'UNKNOWN') return null;
  final action = signal.action.trim().isEmpty ? 'hold' : signal.action.trim();
  return Candidate(
    symbol: symbol,
    score: signal.buyScore?.round(),
    note: signal.reason,
    entryReady: action.toLowerCase() == 'buy',
    actionHint: action,
    blockReason: null,
    buyScore: signal.buyScore,
    action: action,
    result: signal.result,
    status: signal.signalStatus,
    reason: signal.reason,
  );
}

List<Candidate> _dedupeCandidates(Iterable<Candidate> values) {
  final seen = <String>{};
  return [
    for (final candidate in values)
      if (candidate.symbol.trim().isNotEmpty &&
          seen.add(candidate.symbol.trim()))
        candidate,
  ];
}

bool _isHomeKisRecord(
  DashboardController controller,
  String provider,
  String market,
) {
  if (!controller.isKisSelected) return true;
  return provider.trim().toLowerCase() == 'kis' ||
      market.trim().toUpperCase() == 'KR';
}

int? _slotMinutes(String value) {
  final match = RegExp(r'(\d{1,2}):(\d{2})').firstMatch(value);
  if (match == null) return null;
  final hour = int.tryParse(match.group(1)!);
  final minute = int.tryParse(match.group(2)!);
  if (hour == null || minute == null || hour > 23 || minute > 59) {
    return null;
  }
  return hour * 60 + minute;
}

bool _withinSlotTolerance(DateTime value, int targetMinutes) =>
    _slotDistance(value, targetMinutes) <= 15 * 60;

int _slotDistance(DateTime value, int targetMinutes) {
  final seconds = value.hour * 60 * 60 + value.minute * 60 + value.second;
  return (seconds - targetMinutes * 60).abs();
}

bool _sameKstDate(DateTime? value, DateTime other) {
  return value != null &&
      value.year == other.year &&
      value.month == other.month &&
      value.day == other.day;
}

String _displaySymbol(
  DashboardController controller,
  String symbol,
  String? name,
) {
  if (symbol.trim().isEmpty) return '종목 데이터 없음';
  if (!controller.isKisSelected) return symbol.trim();
  final catalogName = KrStockCatalog.shared.displayName(symbol);
  final directName = name?.trim() ?? '';
  final displayName = directName.isEmpty ||
          normalizeKrSymbol(directName) == normalizeKrSymbol(symbol)
      ? catalogName
      : directName;
  return formatKrStockDisplay(
    symbol,
    name: displayName,
  );
}

String _scoreLine(Candidate? candidate, WatchlistRunResult result) {
  if (candidate == null) return 'AI 판단 데이터 없음';
  return _candidateScoreLine(candidate);
}

String _candidateScoreLine(Candidate candidate) {
  final values = <String>[];
  final gpt = candidate.gptBuyScore ?? candidate.aiBuyScore;
  final quant = candidate.quantBuyScore ?? candidate.quantScore;
  final finalScore = candidate.finalEntryScore ??
      candidate.finalBuyScore ??
      candidate.finalScore ??
      candidate.score;
  if (gpt != null) values.add('GPT ${_number(gpt)}');
  if (quant != null) values.add('Quant ${_number(quant)}');
  if (finalScore != null) values.add('Final ${_number(finalScore)}');
  if (candidate.confidence != null) {
    values.add('신뢰도 ${_number(candidate.confidence!)}');
  }
  return values.isEmpty ? '점수 데이터 없음' : values.join(' · ');
}

String _shortReason(Candidate? candidate, WatchlistRunResult result) {
  final value = candidate == null
      ? result.triggerBlockReason.isNotEmpty
          ? result.triggerBlockReason
          : result.reason
      : _shortCandidateReason(candidate);
  return value.trim().isEmpty ? '상세 보기에서 후보 정보를 확인하세요' : value.trim();
}

String _shortCandidateReason(Candidate candidate) {
  for (final value in [
    candidate.reason,
    candidate.note,
    candidate.gptReason,
    candidate.aiReason,
    candidate.whyHold,
    candidate.noOrderReason ?? '',
  ]) {
    if (value.trim().isNotEmpty) return value.trim();
  }
  return '';
}

String _number(num value) {
  final rounded = value % 1 == 0;
  return rounded ? value.toInt().toString() : value.toStringAsFixed(1);
}

List<String> _slots(DashboardController controller) {
  final status = controller.schedulerStatus;
  final values = status.effectiveProfileAnalysisTimes.isNotEmpty
      ? status.effectiveProfileAnalysisTimes
      : status.profileAnalysisTimes;
  return values.where((value) => value.trim().isNotEmpty).toList();
}

String? _latestTime(DashboardController controller) {
  final value = controller.schedulerStatus.lastProfileRunAt ??
      controller.runResult.createdAt ??
      (controller.automationRecentRuns.isEmpty
          ? null
          : controller.automationRecentRuns.first.createdAt);
  final parsed = parseTimestampToKst(value);
  if (parsed == null) return null;
  return '${parsed.hour.toString().padLeft(2, '0')}:${parsed.minute.toString().padLeft(2, '0')}';
}

String _translateBlockReason(String reason) {
  final normalized = reason.trim().toLowerCase();
  const labels = <String, String>{
    'below_profile_buy_threshold': '프로필 최소 매수 점수 미달',
    'weak_final_score_gap': '최종 점수 차이가 부족함',
    'market_closed': '시장 운영 시간이 아님',
    'scheduler_buy_disabled': '스케줄러 매수가 비활성화됨',
    'daily_entry_limit_reached': '일일 진입 한도에 도달함',
    'cash_only': '현금 매수 조건을 확인할 수 없음',
    'duplicate_order': '중복 주문 방지로 차단됨',
  };
  return labels[normalized] ?? reason;
}
