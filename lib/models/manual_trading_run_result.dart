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

  bool get isHold => action.toLowerCase() == 'hold';
  bool get noOrderCreated => orderId == null && relatedOrderId == null;
  bool get riskAllowed => riskApproved == true || approvedByRisk == true;
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
      action: _stringValue(payload['action'] ?? json['action'],
          fallback: 'unknown'),
      reason: _stringValue(payload['reason'] ?? json['reason'] ?? run['reason'],
          fallback: ''),
      quantReason:
          _nullableString(json['quant_reason'] ?? payload['quant_reason']),
      aiReason: _nullableString(json['ai_reason'] ?? payload['ai_reason']),
      signalId: _nullableString(json['signal_id'] ?? payload['signal_id']),
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
      signalStatus:
          _nullableString(json['signal_status'] ?? payload['signal_status']),
      buyScore: _doubleValue(json['buy_score'] ?? payload['buy_score']),
      sellScore: _doubleValue(json['sell_score'] ?? payload['sell_score']),
      confidence: _doubleValue(json['confidence'] ?? payload['confidence']),
      regimeConfidence: _doubleValue(
        json['regime_confidence'] ??
            payload['regime_confidence'] ??
            payload['gpt_market_confidence'],
      ),
      quantBuyScore:
          _doubleValue(json['quant_buy_score'] ?? payload['quant_buy_score']),
      quantSellScore:
          _doubleValue(json['quant_sell_score'] ?? payload['quant_sell_score']),
      aiBuyScore: _doubleValue(json['ai_buy_score'] ?? payload['ai_buy_score']),
      aiSellScore:
          _doubleValue(json['ai_sell_score'] ?? payload['ai_sell_score']),
      finalBuyScore:
          _doubleValue(json['final_buy_score'] ?? payload['final_buy_score']),
      finalSellScore:
          _doubleValue(json['final_sell_score'] ?? payload['final_sell_score']),
      riskFlags: _stringList(json['risk_flags'] ?? payload['risk_flags']),
      gatingNotes: _stringList(json['gating_notes'] ?? payload['gating_notes']),
      indicatorPayload: indicators.map,
      rawIndicatorPayload: indicators.raw,
      hardBlockReason: _nullableString(
          json['hard_block_reason'] ?? payload['hard_block_reason']),
      hardBlocked:
          _boolValue(json['hard_blocked'] ?? payload['hard_blocked']) ?? false,
      createdAt: _nullableString(json['created_at'] ?? payload['created_at']),
      gptContext: GptRiskContext.fromJson(
        json['gpt_context'] ?? payload['gpt_context'],
      ),
    );
  }

  static Map<String, dynamic> _asMap(Object? value) {
    if (value is Map<String, dynamic>) return value;
    return <String, dynamic>{};
  }

  static String _stringValue(Object? value, {required String fallback}) {
    final stringValue = value?.toString();
    if (stringValue == null || stringValue.isEmpty) return fallback;
    return stringValue;
  }

  static String? _nullableString(Object? value) {
    final stringValue = value?.toString();
    if (stringValue == null || stringValue.isEmpty || stringValue == 'null') {
      return null;
    }
    return stringValue;
  }

  static int _intValue(Object? value) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? 0;
  }

  static double? _doubleValue(Object? value) {
    if (value is num) return value.toDouble();
    return double.tryParse(value?.toString() ?? '');
  }

  static bool? _boolValue(Object? value) {
    if (value is bool) return value;
    if (value == null) return null;
    final normalized = value.toString().toLowerCase();
    if (normalized == 'true') return true;
    if (normalized == 'false') return false;
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
