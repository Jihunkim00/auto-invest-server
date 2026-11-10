import 'candidate.dart';

class AutomationTodayDecisions {
  const AutomationTodayDecisions({
    required this.tradeDateKst,
    required this.timezone,
    required this.provider,
    required this.market,
    required this.profileId,
    required this.profileKey,
    required this.profileName,
    required this.ownerUserId,
    required this.profileStatus,
    required this.slots,
    this.executionHistory = const <AutomationTodayDecisionSlot>[],
  });

  static const empty = AutomationTodayDecisions(
    tradeDateKst: '',
    timezone: 'Asia/Seoul',
    provider: null,
    market: null,
    profileId: null,
    profileKey: null,
    profileName: null,
    ownerUserId: null,
    profileStatus: null,
    slots: <AutomationTodayDecisionSlot>[],
  );

  final String tradeDateKst;
  final String timezone;
  final String? provider;
  final String? market;
  final int? profileId;
  final String? profileKey;
  final String? profileName;
  final int? ownerUserId;
  final String? profileStatus;
  final List<AutomationTodayDecisionSlot> slots;
  final List<AutomationTodayDecisionSlot> executionHistory;

  bool get hasProfile => profileId != null;
  bool get isLoadedForToday => tradeDateKst.isNotEmpty;

  List<AutomationTodayDecisionSlot> get executedSlots => slots
      .where((slot) =>
          !slot.isPending &&
          (slot.status != 'no_result' ||
              slot.createdAt != null ||
              slot.schedulerFinishedAt != null))
      .toList()
    ..sort((a, b) {
      final compared = b.resultEpoch.compareTo(a.resultEpoch);
      return compared != 0
          ? compared
          : b.schedulerSlot.compareTo(a.schedulerSlot);
    });

  factory AutomationTodayDecisions.fromJson(Map<String, dynamic> json) {
    final rawSlots = json['slots'];
    return AutomationTodayDecisions(
      tradeDateKst: _string(json['trade_date_kst'] ?? json['tradeDateKst']),
      timezone: _string(json['timezone']).isEmpty
          ? 'Asia/Seoul'
          : _string(json['timezone']),
      provider: _nullableString(json['provider']),
      market: _nullableString(json['market']),
      profileId: _int(json['profile_id'] ?? json['profileId']),
      profileKey: _nullableString(json['profile_key'] ?? json['profileKey']),
      profileName: _nullableString(json['profile_name'] ?? json['profileName']),
      ownerUserId: _int(json['owner_user_id'] ?? json['ownerUserId']),
      profileStatus:
          _nullableString(json['profile_status'] ?? json['profileStatus']),
      slots: rawSlots is List
          ? rawSlots
              .whereType<Map>()
              .map((item) => AutomationTodayDecisionSlot.fromJson(
                    Map<String, dynamic>.from(item),
                  ))
              .toList(growable: false)
          : const <AutomationTodayDecisionSlot>[],
      executionHistory: (json['execution_history'] as List? ?? const [])
          .whereType<Map>()
          .map((item) => AutomationTodayDecisionSlot.fromJson(
                Map<String, dynamic>.from(item),
              ))
          .toList(growable: false),
    );
  }
}

class AutomationTodayDecisionSlot {
  const AutomationTodayDecisionSlot({
    required this.schedulerSlot,
    required this.status,
    required this.signalStatus,
    required this.runId,
    required this.runKey,
    required this.signalId,
    required this.profileId,
    required this.profileKey,
    required this.profileName,
    required this.ownerUserId,
    required this.profileSnapshotId,
    required this.snapshotSourceCount,
    required this.snapshotEligibleCount,
    required this.snapshotSelectedCount,
    required this.runtimeQuantCandidateCount,
    required this.runtimeQuantTop5Symbols,
    required this.gptTargetSymbols,
    required this.gptCompletedSymbols,
    required this.gptFailedSymbols,
    required this.finalCandidateSymbols,
    required this.finalRankedTop5,
    required this.scoreGateCandidates,
    required this.finalSelectedSymbol,
    required this.symbol,
    required this.symbolName,
    required this.action,
    required this.finalBuyScore,
    required this.finalSellScore,
    required this.confidence,
    required this.reason,
    required this.aiReason,
    required this.createdAt,
    required this.createdAtKst,
    required this.quantRank,
    required this.aiRank,
    this.analysisCandidates = const <Candidate>[],
    this.gptBuyScore,
    this.gptAnalysisStatus,
    this.failureStage,
    this.httpStatus,
    this.finalFailureReason,
    this.aiDecision,
    this.orderStatus = 'NOT SUBMITTED',
    this.fillStatus,
    this.orderBlockReason,
    this.schedulerStatus,
    this.schedulerReason,
    this.analysisReason,
    this.scheduledAt,
    this.schedulerFinishedAt,
    this.schedulerOutcomeApplied = true,
  });

  final String schedulerSlot;
  final String status;
  final String? signalStatus;
  final int? runId;
  final String? runKey;
  final int? signalId;
  final int? profileId;
  final String? profileKey;
  final String? profileName;
  final int? ownerUserId;
  final int? profileSnapshotId;
  final int? snapshotSourceCount;
  final int? snapshotEligibleCount;
  final int? snapshotSelectedCount;
  final int runtimeQuantCandidateCount;
  final List<String> runtimeQuantTop5Symbols;
  final List<String> gptTargetSymbols;
  final List<String> gptCompletedSymbols;
  final List<String> gptFailedSymbols;
  final List<String> finalCandidateSymbols;
  final List<Candidate> finalRankedTop5;
  final List<Candidate> scoreGateCandidates;
  final String? finalSelectedSymbol;
  final String? symbol;
  final String? symbolName;
  final String? action;
  final double? finalBuyScore;
  final double? finalSellScore;
  final double? confidence;
  final String? reason;
  final String? aiReason;
  final String? createdAt;
  final String? createdAtKst;
  final int? quantRank;
  final int? aiRank;
  final List<Candidate> analysisCandidates;
  final double? gptBuyScore;
  final String? gptAnalysisStatus;
  final String? failureStage;
  final int? httpStatus;
  final String? finalFailureReason;
  final String? aiDecision;
  final String orderStatus;
  final String? fillStatus;
  final String? orderBlockReason;
  final String? schedulerStatus;
  final String? schedulerReason;
  final String? analysisReason;
  final String? scheduledAt;
  final String? schedulerFinishedAt;
  final bool schedulerOutcomeApplied;

  int get resultEpoch =>
      DateTime.tryParse(createdAt ??
              createdAtKst ??
              schedulerFinishedAt ??
              scheduledAt ??
              '')
          ?.millisecondsSinceEpoch ??
      0;

  List<Candidate> get auditCandidates =>
      scoreGateCandidates.isNotEmpty ? scoreGateCandidates : analysisCandidates;

  bool get hasResult =>
      hasAnalysisResult && (symbol?.trim().isNotEmpty ?? false);
  bool get isFailed => status == 'failed';
  bool get hasAnalysisResult =>
      status == 'result' || status == 'analysis_complete' || isAnalysisHold;
  bool get isQuantHold =>
      status == 'analysis_complete' &&
      gptTargetSymbols.isEmpty &&
      gptCompletedSymbols.isEmpty &&
      !analysisCandidates.any((item) =>
          item.gptUsed == true || item.gptAnalysisStatus == 'completed') &&
      finalCandidateSymbols.isEmpty;
  bool get isPending => status == 'analysis_pending';
  bool get isPositionRefreshPending =>
      (status == 'retry_pending' || status == 'deferred') &&
      hasPositionOrEntryBlock;
  bool get isEntryRecoveryBlocked => status == 'blocked';

  bool get isAnalysisHold =>
      isAiScoreHold ||
      const {
        'no_gpt_completed_execution_candidate',
        'no_completed_gpt_final_candidate',
      }.contains(executionReasonCode);

  bool get isScheduleComplete =>
      executionReasonCode == 'no_remaining_analysis_slot';

  bool get hasPositionOrEntryBlock => const {
        'unresolved_entry_limit_hit',
        'position_state_refresh_pending',
        'position_retry_exit_unresolved',
        'account_snapshot_unavailable',
        'position_state_unavailable_after_entry_slot_grace',
      }.contains(executionReasonCode);

  String? get executionReasonCode {
    const executionBlocks = {
      'unresolved_entry_limit_hit',
      'position_state_refresh_pending',
      'position_retry_exit_unresolved',
      'account_snapshot_unavailable',
      'scheduler_task_timeout',
      'position_state_unavailable_after_entry_slot_grace',
    };
    // A linked order's explicit execution block is independent of its AI score.
    if (executionBlocks.contains(orderBlockReason) &&
        !const {'FILLED', 'SIMULATED'}.contains(orderStatus)) {
      return orderBlockReason;
    }
    final primary = _nullableString(reason) ??
        _nullableString(finalFailureReason) ??
        _nullableString(orderBlockReason);
    if (primary?.startsWith('account_snapshot_retry_pending_') == true) {
      return 'account_snapshot_unavailable';
    }
    return primary;
  }

  bool get isAiScoreHold =>
      executionReasonCode == 'gpt_buy_score_below_threshold';

  String? executionReasonLabel({required bool english}) {
    const ko = {
      'no_gpt_completed_execution_candidate':
          '매수 조건을 충족한 AI 분석 완료 후보가 없어 HOLD했습니다.',
      'unresolved_entry_limit_hit': '미해결 주문으로 신규 매수 한도가 차단됐습니다.',
      'position_state_refresh_pending': '계좌 포지션 확인이 진행 중이어서 신규 매수를 보류했습니다.',
      'position_retry_exit_unresolved': '청산 상태 확인이 완료되지 않아 신규 매수를 차단했습니다.',
      'position_state_unavailable_after_entry_slot_grace':
          '계좌 포지션 확인이 완료되지 않아 신규 매수를 보류했습니다.',
      'account_snapshot_unavailable': '계좌 조회를 완료하지 못해 매수를 차단했습니다.',
      'scheduler_task_timeout': '자동매매 분석 작업이 제한 시간 내 완료되지 않았습니다.',
      'no_remaining_analysis_slot': '오늘 예정된 자동매매 분석이 모두 종료됐습니다.',
      'gpt_buy_score_below_threshold': 'AI 매수 점수가 기준에 미달해 매수를 보류했습니다.',
    };
    const en = {
      'no_gpt_completed_execution_candidate':
          'HOLD: no completed AI candidate met the BUY conditions.',
      'no_remaining_analysis_slot':
          'All scheduled analyses for today have finished.',
      'position_state_unavailable_after_entry_slot_grace':
          'New entries are on hold until account positions are confirmed.',
      'unresolved_entry_limit_hit':
          'An unresolved BUY occupies the new entry limit.',
      'position_state_refresh_pending':
          'This slot resumes after positions are confirmed.',
      'position_retry_exit_unresolved':
          'BUY is blocked until the exit order or retry is resolved.',
      'account_snapshot_unavailable':
          'BUY is blocked because the account snapshot is unavailable.',
      'scheduler_task_timeout':
          'The scheduler task did not finish within its time limit.',
      'gpt_buy_score_below_threshold':
          'BUY is on hold because the AI score is below the threshold.',
    };
    return (english ? en : ko)[executionReasonCode];
  }

  factory AutomationTodayDecisionSlot.fromJson(Map<String, dynamic> json) {
    final analyses = _candidates(json['analysis_candidates']);
    final summaryCandidates = analyses.isNotEmpty
        ? analyses
        : _candidates(json['score_gate_candidates']);
    // Older servers can supply audit rows without top-level summary fields.
    if (json['status'] == 'analysis_complete' &&
        _nullableString(json['symbol']) == null) {
      final completed = summaryCandidates.where(
        (item) => item.gptAnalysisStatus == 'completed',
      );
      if (completed.isNotEmpty) {
        final candidate = completed.first;
        json = {
          ...json,
          'symbol': candidate.symbol,
          'symbol_name': candidate.name,
          'gpt_buy_score': candidate.gptBuyScore ?? candidate.aiBuyScore,
          'gpt_analysis_status': candidate.gptAnalysisStatus,
          'final_buy_score': candidate.finalBuyScore,
          'ai_reason': candidate.aiReason,
          'reason': json['reason'] ?? candidate.blockReason,
        };
      }
    }
    return AutomationTodayDecisionSlot(
      aiDecision: _nullableString(json['ai_decision']),
      orderStatus: _nullableString(json['order_status']) ?? 'NOT SUBMITTED',
      fillStatus: _nullableString(json['fill_status']),
      orderBlockReason: _nullableString(json['order_block_reason']),
      schedulerStatus: _nullableString(json['scheduler_status']),
      schedulerReason: _nullableString(json['execution_reason']),
      analysisReason: _nullableString(json['analysis_reason']),
      scheduledAt: _nullableString(json['scheduled_at']),
      schedulerFinishedAt: _nullableString(json['scheduler_finished_at']),
      schedulerOutcomeApplied: json['scheduler_outcome_applied'] != false,
      analysisCandidates: analyses,
      gptBuyScore: _double(json['gpt_buy_score']),
      gptAnalysisStatus: _nullableString(json['gpt_analysis_status']),
      failureStage: _nullableString(json['failure_stage']),
      httpStatus: _int(json['http_status']),
      finalFailureReason: _nullableString(json['final_failure_reason']),
      schedulerSlot: _string(json['scheduler_slot'] ?? json['schedulerSlot']),
      status: _string(json['status']).isEmpty
          ? 'no_result'
          : _string(json['status']),
      signalStatus:
          _nullableString(json['signal_status'] ?? json['signalStatus']),
      runId: _int(json['run_id'] ?? json['runId']),
      runKey: _nullableString(json['run_key'] ?? json['runKey']),
      signalId: _int(json['signal_id'] ?? json['signalId']),
      profileId: _int(json['profile_id'] ?? json['profileId']),
      profileKey: _nullableString(json['profile_key'] ?? json['profileKey']),
      profileName: _nullableString(json['profile_name'] ?? json['profileName']),
      ownerUserId: _int(json['owner_user_id'] ?? json['ownerUserId']),
      profileSnapshotId: _int(
        json['profile_snapshot_id'] ?? json['profileSnapshotId'],
      ),
      snapshotSourceCount: _int(
        json['snapshot_source_count'] ?? json['snapshotSourceCount'],
      ),
      snapshotEligibleCount: _int(
        json['snapshot_eligible_count'] ?? json['snapshotEligibleCount'],
      ),
      snapshotSelectedCount: _int(
        json['snapshot_selected_count'] ?? json['snapshotSelectedCount'],
      ),
      runtimeQuantCandidateCount: _int(
            json['runtime_quant_candidate_count'] ??
                json['runtimeQuantCandidateCount'],
          ) ??
          0,
      runtimeQuantTop5Symbols: _strings(
        json['runtime_quant_top5_symbols'] ?? json['runtimeQuantTop5Symbols'],
      ),
      gptTargetSymbols: _strings(
        json['gpt_target_symbols'] ?? json['gptTargetSymbols'],
      ),
      gptCompletedSymbols: _strings(
        json['gpt_completed_symbols'] ?? json['gptCompletedSymbols'],
      ),
      gptFailedSymbols: _strings(
        json['gpt_failed_symbols'] ?? json['gptFailedSymbols'],
      ),
      finalCandidateSymbols: _strings(
        json['final_candidate_symbols'] ?? json['finalCandidateSymbols'],
      ),
      finalRankedTop5: _candidates(
        json['final_ranked_top5'] ?? json['finalRankedTop5'],
      ),
      scoreGateCandidates: _candidates(
        json['score_gate_candidates'] ?? json['scoreGateCandidates'],
      ),
      finalSelectedSymbol: _nullableString(
        json['final_selected_symbol'] ?? json['finalSelectedSymbol'],
      ),
      symbol: _nullableString(json['symbol']),
      symbolName: _nullableString(json['symbol_name'] ?? json['symbolName']),
      action: _nullableString(json['action']),
      finalBuyScore: _double(
        json['final_buy_score'] ?? json['finalBuyScore'],
      ),
      finalSellScore: _double(
        json['final_sell_score'] ?? json['finalSellScore'],
      ),
      confidence: _double(json['confidence']),
      reason: _nullableString(json['reason']),
      aiReason: _nullableString(json['ai_reason'] ?? json['aiReason']),
      createdAt: _nullableString(json['created_at'] ?? json['createdAt']),
      createdAtKst: _nullableString(
        json['created_at_kst'] ?? json['createdAtKst'],
      ),
      quantRank: _int(json['quant_rank'] ?? json['quantRank']),
      aiRank: _int(json['ai_rank'] ?? json['aiRank']),
    );
  }
}

List<String> _strings(Object? value) {
  if (value is! List) return const <String>[];
  return value
      .map((item) => item?.toString().trim() ?? '')
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

List<Candidate> _candidates(Object? value) {
  if (value is! List) return const <Candidate>[];
  return value
      .whereType<Map>()
      .map((item) => Candidate.fromJson(Map<String, dynamic>.from(item)))
      .toList(growable: false);
}

String _string(Object? value) => value?.toString().trim() ?? '';

String? _nullableString(Object? value) {
  final result = _string(value);
  return result.isEmpty ? null : result;
}

int? _int(Object? value) {
  if (value is int) return value;
  return int.tryParse(value?.toString() ?? '');
}

double? _double(Object? value) {
  if (value is num) return value.toDouble();
  return double.tryParse(value?.toString() ?? '');
}
