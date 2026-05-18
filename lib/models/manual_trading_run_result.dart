import 'dart:convert';

import 'gpt_risk_context.dart';

class ManualTradingRunResult {
  const ManualTradingRunResult({
    required this.symbol,
    required this.gateLevel,
    required this.gateProfileName,
    required this.action,
    required this.reason,
    required this.quantReason,
    required this.aiReason,
    required this.signalId,
    required this.relatedOrderId,
    required this.orderId,
    required this.riskApproved,
    required this.approvedByRisk,
    required this.brokerStatus,
    required this.internalStatus,
    required this.result,
    required this.runResult,
    required this.runReason,
    required this.signalStatus,
    required this.buyScore,
    required this.sellScore,
    required this.confidence,
    required this.regimeConfidence,
    required this.quantBuyScore,
    required this.quantSellScore,
    required this.aiBuyScore,
    required this.aiSellScore,
    required this.finalBuyScore,
    required this.finalSellScore,
    required this.riskFlags,
    required this.gatingNotes,
    required this.indicatorPayload,
    required this.rawIndicatorPayload,
    required this.hardBlockReason,
    required this.hardBlocked,
    required this.createdAt,
    this.gptContext = GptRiskContext.empty,
    this.scoreDetailsNotReturned = false,
  });

  final String symbol;
  final int gateLevel;
  final String? gateProfileName;
  final String action;
  final String reason;
  final String? quantReason;
  final String? aiReason;
  final String? signalId;
  final String? relatedOrderId;
  final String? orderId;
  final bool? riskApproved;
  final bool? approvedByRisk;
  final String? brokerStatus;
  final String? internalStatus;
  final String result;
  final String? runResult;
  final String? runReason;
  final String? signalStatus;
  final double? buyScore;
  final double? sellScore;
  final double? confidence;
  final double? regimeConfidence;
  final double? quantBuyScore;
  final double? quantSellScore;
  final double? aiBuyScore;
  final double? aiSellScore;
  final double? finalBuyScore;
  final double? finalSellScore;
  final List<String> riskFlags;
  final List<String> gatingNotes;
  final Map<String, dynamic> indicatorPayload;
  final String? rawIndicatorPayload;
  final String? hardBlockReason;
  final bool hardBlocked;
  final String? createdAt;
  final GptRiskContext gptContext;
  final bool scoreDetailsNotReturned;

  bool get isHold => action.toLowerCase() == 'hold';
  bool get noOrderCreated => orderId == null && relatedOrderId == null;
  bool get riskAllowed => riskApproved == true || approvedByRisk == true;
  bool get hasScoreDetails =>
      buyScore != null ||
      sellScore != null ||
      confidence != null ||
      quantBuyScore != null ||
      quantSellScore != null ||
      aiBuyScore != null ||
      aiSellScore != null ||
      finalBuyScore != null ||
      finalSellScore != null;
  String get displayStatus => signalStatus ?? runResult ?? result;
  String get displayOrderId => orderId ?? relatedOrderId ?? 'No order created';
  String get gateLabel {
    final profile = gateProfileName;
    if (profile == null || profile.isEmpty) return 'Gate $gateLevel';
    return 'Gate $gateLevel / $profile';
  }

  factory ManualTradingRunResult.fromJson(Map<String, dynamic> json) {
    final payload = _asMap(json['response_payload']);
    final run = _asMap(json['run']);
    final order = _asMap(payload['order']);
    final risk = _asMap(payload['risk']);
    final signal = _asMap(payload['signal']);
    final scores = _asMap(payload['scores']);
    final signalScores = _asMap(signal['scores']);
    final gptContextMap = _asMap(
      json['gpt_context'] ?? payload['gpt_context'] ?? signal['gpt_context'],
    );
    final indicators = _parseIndicatorPayload(
      payload['indicator_payload'] ?? json['indicator_payload'],
    );

    final relatedOrderId = _nullableString(
        json['related_order_id'] ?? payload['related_order_id']);
    final orderId = _nullableString(
      json['order_id'] ?? payload['order_id'] ?? relatedOrderId,
    );
    final approvedByRisk =
        _boolValue(json['approved_by_risk'] ?? payload['approved_by_risk']);
    final riskApproved =
        _boolValue(risk['approved'] ?? payload['risk_approved']) ??
            approvedByRisk;

    return ManualTradingRunResult(
      symbol: _stringValue(json['symbol'] ?? payload['symbol'],
          fallback: 'UNKNOWN'),
      gateLevel: _intValue(json['gate_level'] ?? payload['gate_level']),
      gateProfileName: _nullableString(
          json['gate_profile_name'] ?? payload['gate_profile_name']),
      action: _stringValue(
          payload['action'] ?? signal['action'] ?? json['action'],
          fallback: 'unknown'),
      reason: _stringValue(
          payload['reason'] ??
              signal['reason'] ??
              json['reason'] ??
              run['reason'],
          fallback: ''),
      quantReason: _nullableString(json['quant_reason'] ??
          payload['quant_reason'] ??
          signal['quant_reason']),
      aiReason: _nullableString(
          json['ai_reason'] ?? payload['ai_reason'] ?? signal['ai_reason']),
      signalId: _nullableString(json['signal_id'] ??
          payload['signal_id'] ??
          signal['signal_id'] ??
          signal['id']),
      relatedOrderId: relatedOrderId,
      orderId: orderId,
      riskApproved: riskApproved,
      approvedByRisk: approvedByRisk,
      brokerStatus: _nullableString(json['broker_status'] ??
          payload['broker_status'] ??
          order['broker_status']),
      internalStatus: _nullableString(json['internal_status'] ??
          payload['internal_status'] ??
          order['internal_status']),
      result: _stringValue(json['result'] ?? payload['result'],
          fallback: 'unknown'),
      runResult: _nullableString(run['result'] ?? json['result']),
      runReason: _nullableString(run['reason'] ?? json['reason']),
      signalStatus: _nullableString(json['signal_status'] ??
          payload['signal_status'] ??
          signal['status']),
      buyScore: _doubleValue(json['buy_score'] ??
          payload['buy_score'] ??
          scores['buy_score'] ??
          signalScores['buy_score']),
      sellScore: _doubleValue(json['sell_score'] ??
          payload['sell_score'] ??
          scores['sell_score'] ??
          signalScores['sell_score']),
      confidence: _doubleValue(json['confidence'] ??
          payload['confidence'] ??
          scores['confidence'] ??
          signalScores['confidence'] ??
          signal['confidence']),
      regimeConfidence: _doubleValue(
        json['regime_confidence'] ??
            payload['regime_confidence'] ??
            payload['gpt_market_confidence'],
      ),
      quantBuyScore: _doubleValue(json['quant_buy_score'] ??
          payload['quant_buy_score'] ??
          scores['quant_buy_score'] ??
          signalScores['quant_buy_score'] ??
          signal['quant_buy_score']),
      quantSellScore: _doubleValue(json['quant_sell_score'] ??
          payload['quant_sell_score'] ??
          scores['quant_sell_score'] ??
          signalScores['quant_sell_score'] ??
          signal['quant_sell_score']),
      aiBuyScore: _doubleValue(json['ai_buy_score'] ??
          payload['ai_buy_score'] ??
          scores['ai_buy_score'] ??
          signalScores['ai_buy_score'] ??
          signal['ai_buy_score']),
      aiSellScore: _doubleValue(json['ai_sell_score'] ??
          payload['ai_sell_score'] ??
          scores['ai_sell_score'] ??
          signalScores['ai_sell_score'] ??
          signal['ai_sell_score']),
      finalBuyScore: _doubleValue(json['final_buy_score'] ??
          payload['final_buy_score'] ??
          scores['final_buy_score'] ??
          signalScores['final_buy_score'] ??
          signal['final_buy_score']),
      finalSellScore: _doubleValue(json['final_sell_score'] ??
          payload['final_sell_score'] ??
          scores['final_sell_score'] ??
          signalScores['final_sell_score'] ??
          signal['final_sell_score']),
      riskFlags: _stringList(json['risk_flags'] ?? payload['risk_flags']),
      gatingNotes: _stringList(json['gating_notes'] ?? payload['gating_notes']),
      indicatorPayload: indicators.map,
      rawIndicatorPayload: indicators.raw,
      hardBlockReason: _nullableString(
          json['hard_block_reason'] ?? payload['hard_block_reason']),
      hardBlocked:
          _boolValue(json['hard_blocked'] ?? payload['hard_blocked']) ?? false,
      createdAt: _nullableString(json['created_at'] ?? payload['created_at']),
      gptContext: GptRiskContext.fromJson(gptContextMap),
    );
  }

  ManualTradingRunResult mergeSignalPayload(Map<String, dynamic> signal) {
    final signalMap = _asMap(signal['signal']);
    final scores = _asMap(signal['scores']);
    final mergedSignal = signalMap.isEmpty ? signal : signalMap;
    final mergedScores = scores.isEmpty ? signal : scores;
    final signalGptContext = GptRiskContext.fromJson(
      signal['gpt_context'] ?? mergedSignal['gpt_context'],
    );

    return ManualTradingRunResult(
      symbol: symbol,
      gateLevel: gateLevel,
      gateProfileName: gateProfileName,
      action: _stringValue(mergedSignal['action'] ?? signal['action'],
          fallback: action),
      reason: _stringValue(mergedSignal['reason'] ?? signal['reason'] ?? reason,
          fallback: reason),
      quantReason: _nullableString(
              mergedSignal['quant_reason'] ?? signal['quant_reason']) ??
          quantReason,
      aiReason:
          _nullableString(mergedSignal['ai_reason'] ?? signal['ai_reason']) ??
              aiReason,
      signalId: signalId,
      relatedOrderId: relatedOrderId ??
          _nullableString(signal['related_order_id'] ?? signal['order_id']),
      orderId: orderId,
      riskApproved: riskApproved,
      approvedByRisk: approvedByRisk,
      brokerStatus: brokerStatus,
      internalStatus: internalStatus,
      result: _stringValue(signal['result'], fallback: result),
      runResult: runResult,
      runReason: runReason,
      signalStatus:
          _nullableString(signal['signal_status'] ?? signal['status']) ??
              signalStatus,
      buyScore: buyScore ?? _doubleValue(mergedScores['buy_score']),
      sellScore: sellScore ?? _doubleValue(mergedScores['sell_score']),
      confidence: confidence ?? _doubleValue(mergedScores['confidence']),
      regimeConfidence: regimeConfidence,
      quantBuyScore:
          quantBuyScore ?? _doubleValue(mergedScores['quant_buy_score']),
      quantSellScore:
          quantSellScore ?? _doubleValue(mergedScores['quant_sell_score']),
      aiBuyScore: aiBuyScore ?? _doubleValue(mergedScores['ai_buy_score']),
      aiSellScore: aiSellScore ?? _doubleValue(mergedScores['ai_sell_score']),
      finalBuyScore:
          finalBuyScore ?? _doubleValue(mergedScores['final_buy_score']),
      finalSellScore:
          finalSellScore ?? _doubleValue(mergedScores['final_sell_score']),
      riskFlags:
          _dedupeStringList(riskFlags + _stringList(signal['risk_flags'])),
      gatingNotes:
          _dedupeStringList(gatingNotes + _stringList(signal['gating_notes'])),
      indicatorPayload: indicatorPayload,
      rawIndicatorPayload: rawIndicatorPayload,
      hardBlockReason:
          hardBlockReason ?? _nullableString(signal['hard_block_reason']),
      hardBlocked: hardBlocked || (_boolValue(signal['hard_blocked']) ?? false),
      createdAt: createdAt,
      gptContext: gptContext.hasDetails ? gptContext : signalGptContext,
      scoreDetailsNotReturned: false,
    );
  }

  ManualTradingRunResult markScoreDetailsNotReturned() {
    return ManualTradingRunResult(
      symbol: symbol,
      gateLevel: gateLevel,
      gateProfileName: gateProfileName,
      action: action,
      reason: reason,
      quantReason: quantReason,
      aiReason: aiReason,
      signalId: signalId,
      relatedOrderId: relatedOrderId,
      orderId: orderId,
      riskApproved: riskApproved,
      approvedByRisk: approvedByRisk,
      brokerStatus: brokerStatus,
      internalStatus: internalStatus,
      result: result,
      runResult: runResult,
      runReason: runReason,
      signalStatus: signalStatus,
      buyScore: buyScore,
      sellScore: sellScore,
      confidence: confidence,
      regimeConfidence: regimeConfidence,
      quantBuyScore: quantBuyScore,
      quantSellScore: quantSellScore,
      aiBuyScore: aiBuyScore,
      aiSellScore: aiSellScore,
      finalBuyScore: finalBuyScore,
      finalSellScore: finalSellScore,
      riskFlags: riskFlags,
      gatingNotes: gatingNotes,
      indicatorPayload: indicatorPayload,
      rawIndicatorPayload: rawIndicatorPayload,
      hardBlockReason: hardBlockReason,
      hardBlocked: hardBlocked,
      createdAt: createdAt,
      gptContext: gptContext,
      scoreDetailsNotReturned: true,
    );
  }

  static Map<String, dynamic> _asMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    if (value is Map) return Map<String, dynamic>.from(value);
    return <String, dynamic>{};
  }

  static String _stringValue(Object? value, {required String fallback}) {
    final stringValue = value?.toString().trim();
    if (stringValue == null || stringValue.isEmpty || stringValue == 'null') {
      return fallback;
    }
    return stringValue;
  }

  static String? _nullableString(Object? value) {
    final stringValue = value?.toString().trim();
    if (stringValue == null || stringValue.isEmpty || stringValue == 'null') {
      return null;
    }
    return stringValue;
  }

  static int _intValue(Object? value) {
    if (value is num) return value.toInt();
    final text = value?.toString().trim().replaceAll(',', '');
    if (text == null || text.isEmpty || text == 'null') return 0;
    return int.tryParse(text) ?? double.tryParse(text)?.toInt() ?? 0;
  }

  static double? _doubleValue(Object? value) {
    if (value is num) return value.toDouble();
    final text = value?.toString().trim().replaceAll(',', '');
    if (text == null || text.isEmpty || text == 'null') return null;
    return double.tryParse(text);
  }

  static bool? _boolValue(Object? value) {
    if (value is bool) return value;
    if (value == null) return null;
    if (value is num) return value != 0;
    final normalized = value.toString().trim().toLowerCase();
    if (normalized == 'true' || normalized == '1' || normalized == 'yes') {
      return true;
    }
    if (normalized == 'false' || normalized == '0' || normalized == 'no') {
      return false;
    }
    return null;
  }

  static List<String> _stringList(Object? value) {
    Object? parsed = value;
    if (value is String) {
      try {
        parsed = jsonDecode(value);
      } catch (_) {
        parsed = value.isEmpty ? <Object>[] : <Object>[value];
      }
    }
    if (parsed is List) {
      return parsed
          .map((item) => item?.toString() ?? '')
          .where((item) => item.isNotEmpty)
          .toList();
    }
    return <String>[];
  }

  static List<String> _dedupeStringList(List<String> values) {
    final result = <String>[];
    for (final value in values) {
      final text = value.trim();
      if (text.isNotEmpty && !result.contains(text)) {
        result.add(text);
      }
    }
    return result;
  }

  static _ParsedIndicatorPayload _parseIndicatorPayload(Object? value) {
    if (value is Map<String, dynamic>) {
      return _ParsedIndicatorPayload(map: value);
    }
    if (value is String && value.isNotEmpty) {
      try {
        final decoded = jsonDecode(value);
        if (decoded is Map<String, dynamic>) {
          return _ParsedIndicatorPayload(map: decoded);
        }
      } catch (_) {
        return _ParsedIndicatorPayload(raw: value);
      }
      return _ParsedIndicatorPayload(raw: value);
    }
    return const _ParsedIndicatorPayload();
  }
}

class _ParsedIndicatorPayload {
  const _ParsedIndicatorPayload({
    this.map = const <String, dynamic>{},
    this.raw,
  });

  final Map<String, dynamic> map;
  final String? raw;
}
