import 'dart:convert';

import 'package:http/http.dart' as http;

import '../config/app_config.dart';
import '../../models/agent_chat_conversation.dart';
import '../../models/agent_chat_live_order_action.dart';
import '../../models/agent_chat_message.dart';
import '../../models/agent_chat_send_response.dart';
import '../../models/agent_command.dart';
import '../../models/agent_operations.dart';
import '../../models/agent_plan.dart';
import '../../models/agent_review_queue.dart';
import '../../models/agent_run.dart';
import '../../models/candidate.dart';
import '../../models/agent_live_prefill.dart';
import '../../models/kis_auto_readiness.dart';
import '../../models/kis_auto_simulator_result.dart';
import '../../models/kis_buy_shadow_decision.dart';
import '../../models/kis_exit_shadow_decision.dart';
import '../../models/kis_limited_auto_buy.dart';
import '../../models/kis_limited_auto_buy_execution_review.dart';
import '../../models/kis_limited_auto_buy_review.dart';
import '../../models/kis_limited_auto_sell.dart';
import '../../models/kis_single_symbol_trading_result.dart';
import '../../models/kis_shadow_exit_review.dart';
import '../../models/kis_shadow_exit_review_queue.dart';
import '../../models/kis_live_exit_preflight.dart';
import '../../models/kis_scheduler_dry_run_orchestration.dart';
import '../../models/kis_scheduler_dry_run_review.dart';
import '../../models/kis_scheduler_guarded_sell.dart';
import '../../models/kis_scheduler_guarded_buy.dart';
import '../../models/kis_scheduler_guarded_sell_review.dart';
import '../../models/kis_scheduler_readiness.dart';
import '../../models/kis_scheduler_simulation.dart';
import '../../models/kis_scheduler_live.dart';
import '../../models/kis_manual_order_result.dart';
import '../../models/kis_manual_order_safety_status.dart';
import '../../models/log_items.dart';
import '../../models/managed_position.dart';
import '../../models/market_watchlist.dart';
import '../../models/manual_trading_run_result.dart';
import '../../models/order_validation_result.dart';
import '../../models/ops_production_readiness.dart';
import '../../models/ops_settings.dart';
import '../../models/portfolio_summary.dart';
import '../../models/scheduler_status.dart';
import '../../models/trading_run.dart';
import '../../models/watchlist_run_result.dart';

class ApiRequestException implements Exception {
  const ApiRequestException(this.message, {this.statusCode, this.detail});

  final String message;
  final int? statusCode;
  final Map<String, dynamic>? detail;

  @override
  String toString() => message;
}

class ApiClient {
  ApiClient({http.Client? client}) : _client = client ?? http.Client();

  final http.Client _client;
  static const _kisLiveConfirmationPhrase =
      'I UNDERSTAND THIS WILL PLACE A REAL KIS ORDER';

  static int _readInt(Object? value, int fallback) {
    if (value is num) return value.toInt();
    return int.tryParse(value?.toString() ?? '') ?? fallback;
  }

  static double? _readNullableDouble(Object? value) {
    if (value == null) return null;
    if (value is num) return value.toDouble();
    final text = value.toString().trim().replaceAll(',', '');
    if (text.isEmpty) return null;
    return double.tryParse(text);
  }

  static String? _readNullableString(Object? value) {
    final text = value?.toString().trim();
    if (text == null || text.isEmpty) return null;
    return text;
  }

  static bool _looksLikeTokenExpired(String? value) {
    final text = value?.toLowerCase() ?? '';
    return text.contains('egw00123') ||
        text.contains('token expired') ||
        text.contains('expired token') ||
        text.contains('기간이 만료된 token') ||
        text.contains('만료된 token');
  }

  Future<Map<String, dynamic>> _getJson(String path) async {
    final r = await _client.get(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _getJsonNoCache(String path) async {
    final baseUri = Uri.parse('${AppConfig.baseUrl}$path');
    final queryParameters = Map<String, String>.from(baseUri.queryParameters);
    queryParameters['_ts'] = DateTime.now().millisecondsSinceEpoch.toString();
    final uri = baseUri.replace(queryParameters: queryParameters);
    final r = await _client.get(uri, headers: const {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    });
    if (r.statusCode >= 400) {
      throw _apiRequestExceptionFromResponse(r);
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<Map<String, dynamic>> _postJson(String path) async {
    final r = await _client.post(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
    return jsonDecode(r.body) as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> _postJsonBody(
      String path, Map<String, dynamic> body) async {
    final r = await _client.post(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<Map<String, dynamic>> _putJsonBody(
      String path, Map<String, dynamic> body) async {
    final r = await _client.put(
      Uri.parse('${AppConfig.baseUrl}$path'),
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(body),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<void> _post(String path) async {
    final r = await _client.post(Uri.parse('${AppConfig.baseUrl}$path'));
    if (r.statusCode >= 400) throw Exception('HTTP ${r.statusCode}: ${r.body}');
  }

  Future<PortfolioSummary> fetchPortfolioSummary() async {
    final uri = Uri.parse('${AppConfig.baseUrl}/portfolio/summary').replace(
      queryParameters: {
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );

    try {
      final r = await _client.get(uri, headers: const {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
      });
      if (r.statusCode == 404 || r.statusCode == 204) {
        return PortfolioSummary.empty();
      }
      if (r.statusCode >= 400) {
        throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
      }

      final decoded = jsonDecode(r.body);
      if (decoded is! Map) {
        throw const ApiRequestException('Invalid portfolio summary response.');
      }

      return PortfolioSummary.fromJson(Map<String, dynamic>.from(decoded));
    } on http.ClientException {
      return PortfolioSummary.empty();
    }
  }

  Future<PortfolioSummary> fetchUsPortfolioSummary() => fetchPortfolioSummary();
  Future<PortfolioSummary> fetchPortfolioSummaryForMarket(String market) {
    return market.trim().toUpperCase() == 'KR'
        ? fetchKrPortfolioSummary()
        : fetchUsPortfolioSummary();
  }

  Future<PortfolioSummary> fetchKrPortfolioSummary() async {
    final balanceResult =
        await _fetchKrPortfolioEndpoint('/kis/account/balance');
    final positionsResult =
        await _fetchKrPortfolioEndpoint('/kis/account/positions');
    final ordersResult =
        await _fetchKrPortfolioEndpoint('/kis/account/open-orders');

    final balance = balanceResult.payload;
    final positionsPayload = positionsResult.payload;
    final ordersPayload = ordersResult.payload;

    final rawPositions =
        positionsPayload?['positions'] as List<dynamic>? ?? const [];
    final positions = rawPositions
        .whereType<Map>()
        .map((item) => PositionSummary.fromJson(
            Map<String, dynamic>.from(item.cast<String, dynamic>())))
        .map(_normalizeKrPositionSummary)
        .toList();

    final rawOrders = ordersPayload?['orders'] as List<dynamic>? ?? const [];
    final pendingOrders = rawOrders
        .whereType<Map>()
        .map((item) => PendingOrderSummary.fromJson(
            Map<String, dynamic>.from(item.cast<String, dynamic>())))
        .toList();

    final summedCostBasis = positions.fold<double>(
        0, (total, position) => total + position.costBasis);
    final summedMarketValue = positions.fold<double>(
        0, (total, position) => total + position.marketValue);
    final summedUnrealizedPl = positions.fold<double>(
        0, (total, position) => total + position.unrealizedPl);

    final totalCostBasis =
        _readNullableDouble(balance?['purchase_amount']) ?? summedCostBasis;
    final totalMarketValue =
        _readNullableDouble(balance?['stock_evaluation_amount']) ??
            _readNullableDouble(balance?['total_market_value']) ??
            _readNullableDouble(balance?['total_asset_value']) ??
            summedMarketValue;
    final totalUnrealizedPl =
        _readNullableDouble(balance?['unrealized_pl']) ?? summedUnrealizedPl;
    final totalUnrealizedPlpc =
        totalCostBasis > 0 ? totalUnrealizedPl / totalCostBasis : 0.0;
    final cashValue = _readNullableDouble(balance?['cash']) ??
        _readNullableDouble(balance?['dnca_tot_amt']);
    final authDetails = _krPortfolioAuthDetails([
      balanceResult.error,
      positionsResult.error,
      ordersResult.error,
    ]);

    return PortfolioSummary(
      currency: 'KRW',
      positionsCount: _readInt(positionsPayload?['count'], positions.length),
      pendingOrdersCount:
          _readInt(ordersPayload?['count'], pendingOrders.length),
      totalCostBasis: totalCostBasis,
      totalMarketValue: totalMarketValue,
      totalUnrealizedPl: totalUnrealizedPl,
      totalUnrealizedPlpc: totalUnrealizedPlpc,
      cash: cashValue ?? 0,
      positions: positions,
      pendingOrders: pendingOrders,
      cashKnown: balance != null,
      balanceUnavailable: balance == null,
      positionsUnavailable: positionsPayload == null,
      openOrdersUnavailable: ordersPayload == null,
      kisAuthErrorMessage: authDetails.message,
      nextRefreshAllowedAt: authDetails.nextRefreshAllowedAt,
      tokenExpired: authDetails.tokenExpired,
    );
  }

  Future<_KrPortfolioEndpointResult> _fetchKrPortfolioEndpoint(
      String path) async {
    try {
      return _KrPortfolioEndpointResult.success(await _getJsonNoCache(path));
    } on ApiRequestException catch (error) {
      return _KrPortfolioEndpointResult.failure(error);
    } on http.ClientException catch (error) {
      return _KrPortfolioEndpointResult.failure(
        ApiRequestException('KIS endpoint unavailable: ${error.message}'),
      );
    } on FormatException catch (_) {
      return _KrPortfolioEndpointResult.failure(
        const ApiRequestException('Invalid KIS endpoint response.'),
      );
    }
  }

  _KrPortfolioAuthDetails _krPortfolioAuthDetails(
      Iterable<ApiRequestException?> errors) {
    var tokenExpired = false;
    String? nextRefreshAllowedAt;
    String? refreshGuardReason;
    String? msgCd;
    String? msg1;

    for (final error in errors.whereType<ApiRequestException>()) {
      final detail = error.detail ?? _apiErrorDetailFromMessage(error.message);
      final code = _readNullableString(detail['msg_cd']);
      final message = _readNullableString(detail['msg1']);
      if (msgCd == null && code != null) msgCd = code;
      if (msg1 == null && message != null) msg1 = message;
      if (nextRefreshAllowedAt == null) {
        nextRefreshAllowedAt =
            _readNullableString(detail['next_refresh_allowed_at']);
      }
      if (refreshGuardReason == null) {
        refreshGuardReason =
            _readNullableString(detail['refresh_guard_reason']);
      }
      tokenExpired = tokenExpired ||
          code == 'EGW00123' ||
          _looksLikeTokenExpired(message) ||
          _looksLikeTokenExpired(error.message);
    }

    if (!tokenExpired && msgCd == null && msg1 == null) {
      return const _KrPortfolioAuthDetails();
    }

    final message = tokenExpired
        ? 'KIS token expired. Portfolio data is unavailable until token refresh succeeds.'
        : [msgCd, msg1].whereType<String>().join(' ').trim();
    return _KrPortfolioAuthDetails(
      message: message.isEmpty ? 'KIS portfolio data is unavailable.' : message,
      nextRefreshAllowedAt:
          refreshGuardReason == 'too_recent' ? nextRefreshAllowedAt : null,
      tokenExpired: tokenExpired,
    );
  }

  Future<List<ManagedPosition>> fetchKisManagedPositions() async {
    final payload = await _getJsonNoCache('/kis/positions/manage');
    return KisManagedPositions.fromJson(payload).positions;
  }

  Future<ManualSellPreparation> prepareKisManualSell(String symbol) async {
    final normalized = symbol.trim();
    final payload = await _postJsonBody(
      '/kis/positions/$normalized/prepare-manual-sell',
      const {},
    );
    return ManualSellPreparation.fromJson(payload);
  }

  Future<AgentCommandParseResult> parseAgentCommand({
    required String message,
    String? conversationId,
    Map<String, dynamic>? context,
  }) async {
    final payload = await _postJsonBody('/agent/commands/parse', {
      if (conversationId != null) 'conversation_id': conversationId,
      'message': message,
      'context': context ?? const <String, dynamic>{},
    });
    return AgentCommandParseResult.fromJson(payload);
  }

  Future<AgentChatSendResponse> sendAgentChatMessage({
    required String message,
    String? conversationKey,
    Map<String, dynamic>? context,
    bool autoCreateConversation = true,
  }) async {
    final payload = await _postJsonBody('/agent/chat/send', {
      'conversation_key': conversationKey,
      'message': message,
      'context': context ?? const <String, dynamic>{},
      'auto_create_conversation': autoCreateConversation,
    });
    return AgentChatSendResponse.fromJson(payload);
  }

  Future<AgentChatLiveOrderResponse> confirmAgentChatLiveOrder(
    AgentChatLiveOrderAction action,
  ) async {
    final payload = await _postJsonBody(
      '/agent/chat/live-orders/${action.actionId}/confirm',
      {
        'confirmation': true,
        if (action.confirmationToken != null)
          'confirmation_token': action.confirmationToken,
        if (action.confirmationPhrase != null)
          'confirmation_phrase': action.confirmationPhrase,
        'user_acknowledged_live_order': true,
      },
    );
    return AgentChatLiveOrderResponse.fromJson(payload);
  }

  Future<AgentChatLiveOrderResponse> cancelAgentChatLiveOrder(
    int actionId,
  ) async {
    final payload = await _postJsonBody(
      '/agent/chat/live-orders/$actionId/cancel',
      const {},
    );
    return AgentChatLiveOrderResponse.fromJson(payload);
  }

  Future<AgentChatLiveOrderAction> fetchAgentChatLiveOrder(int actionId) async {
    final payload = await _getJsonNoCache('/agent/chat/live-orders/$actionId');
    return AgentChatLiveOrderAction.fromJson(payload);
  }

  Future<List<AgentChatLiveOrderAction>> fetchRecentAgentChatLiveOrders({
    int limit = 20,
    String? status,
    String? symbol,
    String? conversationKey,
  }) async {
    final params = <String>[
      'limit=$limit',
      if (status != null && status.trim().isNotEmpty)
        'status=${Uri.encodeQueryComponent(status.trim())}',
      if (symbol != null && symbol.trim().isNotEmpty)
        'symbol=${Uri.encodeQueryComponent(symbol.trim())}',
      if (conversationKey != null && conversationKey.trim().isNotEmpty)
        'conversation_key=${Uri.encodeQueryComponent(conversationKey.trim())}',
    ];
    final payload = await _getJsonNoCache(
      '/agent/chat/live-orders/recent?${params.join('&')}',
    );
    final items = payload['actions'] as List<dynamic>? ?? const [];
    return [
      for (final item in items)
        if (item is Map)
          AgentChatLiveOrderAction.fromJson(Map<String, dynamic>.from(item)),
    ];
  }

  Future<AgentChatLiveOrderResponse> syncAgentChatLiveOrder(
    int actionId,
  ) async {
    final payload = await _postJsonBody(
      '/agent/chat/live-orders/$actionId/sync',
      const {},
    );
    return AgentChatLiveOrderResponse.fromJson(payload);
  }

  Future<AgentChatConversation> createAgentChatConversation({
    String? title,
    String source = 'flutter_dashboard',
    Map<String, dynamic>? metadata,
  }) async {
    final payload = await _postJsonBody('/agent/chat/conversations', {
      'title': title,
      'source': source,
      'metadata': metadata ?? const <String, dynamic>{},
    });
    return AgentChatConversation.fromJson(
      Map<String, dynamic>.from(payload['conversation'] as Map),
    );
  }

  Future<List<AgentChatConversation>> fetchAgentChatConversations({
    String status = 'active',
    int limit = 20,
  }) async {
    final payload = await _getJsonNoCache(
      '/agent/chat/conversations?status=$status&limit=$limit',
    );
    return AgentChatConversationList.fromJson(payload).conversations;
  }

  Future<AgentChatConversation> fetchAgentChatConversation(
    String conversationKey,
  ) async {
    final payload = await _getJsonNoCache(
      '/agent/chat/conversations/$conversationKey',
    );
    return AgentChatConversation.fromJson(
      Map<String, dynamic>.from(payload['conversation'] as Map),
    );
  }

  Future<List<AgentChatMessage>> fetchAgentChatMessages(
    String conversationKey, {
    int limit = 100,
    int? beforeId,
  }) async {
    final path = beforeId == null
        ? '/agent/chat/conversations/$conversationKey/messages?limit=$limit'
        : '/agent/chat/conversations/$conversationKey/messages?limit=$limit&before_id=$beforeId';
    final payload = await _getJsonNoCache(path);
    final items = payload['messages'] as List<dynamic>? ?? const [];
    return items
        .whereType<Map>()
        .map((item) =>
            AgentChatMessage.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<AgentChatMessage> appendAgentChatMessage({
    required String conversationKey,
    required String role,
    required String text,
    String messageType = 'plain_text',
    String status = 'completed',
    int? commandLogId,
    int? planId,
    int? planRunId,
    int? authApprovalRequestId,
    int? prefillSourcePlanId,
    String? modelName,
    String? parserStatus,
    Map<String, dynamic>? safety,
    Map<String, dynamic>? metadata,
  }) async {
    final payload = await _postJsonBody(
      '/agent/chat/conversations/$conversationKey/messages',
      {
        'role': role,
        'text': text,
        'message_type': messageType,
        'status': status,
        'command_log_id': commandLogId,
        'plan_id': planId,
        'plan_run_id': planRunId,
        'auth_approval_request_id': authApprovalRequestId,
        'prefill_source_plan_id': prefillSourcePlanId,
        'model_name': modelName,
        'parser_status': parserStatus,
        'safety': safety ?? const <String, dynamic>{},
        'metadata': metadata ?? const <String, dynamic>{},
      },
    );
    return AgentChatMessage.fromJson(
      Map<String, dynamic>.from(payload['message'] as Map),
    );
  }

  Future<AgentChatConversation> archiveAgentChatConversation(
    String conversationKey,
  ) async {
    final payload = await _postJsonBody(
      '/agent/chat/conversations/$conversationKey/archive',
      const {},
    );
    return AgentChatConversation.fromJson(
      Map<String, dynamic>.from(payload['conversation'] as Map),
    );
  }

  Future<AgentChatConversation> clearAgentChatConversation(
    String conversationKey,
  ) async {
    final payload = await _postJsonBody(
      '/agent/chat/conversations/$conversationKey/clear',
      const {},
    );
    return AgentChatConversation.fromJson(
      Map<String, dynamic>.from(payload['conversation'] as Map),
    );
  }

  Future<AgentOperationsSnapshot> fetchAgentOperationsSummary() async {
    final payload = await _getJsonNoCache('/agent/operations/summary');
    return AgentOperationsSnapshot.fromJson(payload);
  }

  Future<AgentReviewQueue> fetchAgentReviewQueue({
    String status = 'open',
    String queueType = 'all',
    String? conversationKey,
    int limit = 50,
  }) async {
    final params = <String>[
      'status=$status',
      'queue_type=$queueType',
      'limit=$limit',
      if (conversationKey != null && conversationKey.trim().isNotEmpty)
        'conversation_key=${Uri.encodeQueryComponent(conversationKey.trim())}',
    ];
    final payload = await _getJsonNoCache(
      '/agent/operations/review-queue?${params.join('&')}',
    );
    return AgentReviewQueue.fromJson(payload);
  }

  Future<AgentReviewQueueStateResult> markAgentReviewQueueItemReviewed(
    String queueKey, {
    String? reviewerNote,
  }) async {
    final payload = await _postJsonBody(
      '/agent/operations/review-queue/$queueKey/reviewed',
      {
        if (reviewerNote != null) 'reviewer_note': reviewerNote,
      },
    );
    return AgentReviewQueueStateResult.fromJson(payload);
  }

  Future<AgentReviewQueueStateResult> dismissAgentReviewQueueItem(
    String queueKey, {
    String? reviewerNote,
  }) async {
    final payload = await _postJsonBody(
      '/agent/operations/review-queue/$queueKey/dismiss',
      {
        if (reviewerNote != null) 'reviewer_note': reviewerNote,
      },
    );
    return AgentReviewQueueStateResult.fromJson(payload);
  }

  Future<AgentPlanCreateResult> createAgentPlanFromCommand(
    int commandLogId, {
    String? planTitle,
    int expiresInMinutes = 60,
  }) async {
    final payload = await _postJsonBody(
      '/agent/plans/from-command/$commandLogId',
      {
        if (planTitle != null) 'plan_title': planTitle,
        'expires_in_minutes': expiresInMinutes,
      },
    );
    return AgentPlanCreateResult.fromJson(payload);
  }

  Future<AgentPlanRunResult> runAgentPlan(
    int planId, {
    String? operatorNote,
  }) async {
    final payload = await _postJsonBody('/agent/plans/$planId/run', {
      'dry_run': true,
      'trigger_source': 'flutter_agent_chat',
      if (operatorNote != null) 'operator_note': operatorNote,
    });
    return AgentPlanRunResult.fromJson(payload);
  }

  Future<AgentLivePrefill> prepareAgentManualTicket(
    int planId, {
    String? operatorNote,
    bool requireAuthApproval = true,
  }) async {
    final payload = await _postJsonBody(
      '/agent/plans/$planId/prepare-manual-ticket',
      {
        'operator_note': operatorNote,
        'require_auth_approval': requireAuthApproval,
      },
    );
    return AgentLivePrefill.fromJson(payload);
  }

  Future<MarketWatchlist> fetchMarketWatchlist(String market) async {
    final normalizedMarket = market.trim().toUpperCase();
    try {
      final payload =
          await _getJsonNoCache('/market-profiles/$normalizedMarket/watchlist');
      return MarketWatchlist.fromJson(payload);
    } catch (_) {
      return MarketWatchlist.empty(normalizedMarket);
    }
  }

  Future<KisManualOrderSafetyStatus> fetchKisManualOrderSafetyStatus() async {
    final payload = await _getJsonNoCache('/kis/manual-order/status');
    return KisManualOrderSafetyStatus.fromJson(payload);
  }

  Future<OrderValidationResult> validateKisOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    Map<String, dynamic>? sourceMetadata,
  }) async {
    final auditMetadata = _safeKisAuditSourceMetadata(sourceMetadata);
    final body = {
      'market': 'KR',
      'symbol': symbol.trim(),
      'side': side.trim().toLowerCase(),
      'qty': qty,
      'order_type': orderType,
      'dry_run': true,
      'reason': 'manual Flutter dashboard dry-run',
      if (auditMetadata.isNotEmpty) 'source_metadata': auditMetadata,
    };
    final payload = await _postJsonBody('/kis/orders/validate', body);
    return OrderValidationResult.fromJson(payload);
  }

  Future<KisManualOrderResult> submitKisManualOrder({
    required String symbol,
    required String side,
    required int qty,
    String orderType = 'market',
    required bool confirmLive,
    Map<String, dynamic>? sourceMetadata,
  }) async {
    final auditMetadata = _safeKisAuditSourceMetadata(sourceMetadata);
    final body = {
      'market': 'KR',
      'symbol': symbol.trim(),
      'side': side.trim().toLowerCase(),
      'qty': qty,
      'order_type': orderType,
      'dry_run': false,
      'confirm_live': confirmLive,
      'confirmation': confirmLive ? _kisLiveConfirmationPhrase : null,
      'reason': 'manual Flutter dashboard live KIS order',
      if (auditMetadata.isNotEmpty) 'source_metadata': auditMetadata,
    };
    final payload = await _postJsonBody('/kis/orders/manual-submit', body);
    return KisManualOrderResult.fromJson(payload);
  }

  Future<KisManualOrderResult> syncKisOrder(int orderId) async {
    final payload = await _postJsonBody('/kis/orders/$orderId/sync', const {});
    return KisManualOrderResult.fromJson(payload);
  }

  Future<KisOpenOrderSyncResult> syncOpenKisOrders() async {
    final payload = await _postJsonBody('/kis/orders/sync-open', const {});
    return KisOpenOrderSyncResult.fromJson(payload);
  }

  Future<Map<String, dynamic>> cancelKisOrder(int orderId) async {
    return _postJsonBody('/kis/orders/$orderId/cancel', const {});
  }

  Future<KisOrderSummary> fetchKisOrderSummary() async {
    final payload = await _getJsonNoCache('/kis/orders/summary');
    return KisOrderSummary.fromJson(payload);
  }

  Future<List<KisManualOrderResult>> fetchKisOrders({
    int limit = 20,
    bool includeRejected = false,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/orders').replace(
      queryParameters: {
        'limit': limit.toString(),
        if (includeRejected) 'include_rejected': 'true',
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );
    final r = await _client.get(uri, headers: const {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    });
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid KIS orders response.');
    }
    final rawOrders = decoded['orders'] as List<dynamic>? ?? const [];
    return rawOrders
        .whereType<Map>()
        .map((item) =>
            KisManualOrderResult.fromJson(Map<String, dynamic>.from(item)))
        .toList();
  }

  Future<KisManualOrderResult> fetchKisOrderDetail(
    int orderId, {
    bool includeSyncPayload = false,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/orders/$orderId').replace(
      queryParameters: {
        if (includeSyncPayload) 'include_sync_payload': 'true',
        '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
      },
    );
    final r = await _client.get(uri);
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    return KisManualOrderResult.fromJson(
        Map<String, dynamic>.from(jsonDecode(r.body) as Map));
  }

  Future<WatchlistRunResult> runKisWatchlistPreview({
    required int gateLevel,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/watchlist/preview').replace(
      queryParameters: {'gate_level': gateLevel.toString()},
    );
    final r = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(const {}),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    final payload = Map<String, dynamic>.from(decoded);
    return WatchlistRunResult.fromJson(payload);
  }

  Future<Map<String, dynamic>> previewKosdaqTop50Watchlist() async {
    return _getJsonNoCache('/kis/watchlist/kosdaq-top50/preview');
  }

  Future<Map<String, dynamic>> updateKosdaqTop50Watchlist() async {
    return _postJsonBody('/kis/watchlist/kosdaq-top50/update', const {});
  }

  Future<KisAutoSimulatorResult> runKisDryRunAuto({
    required int gateLevel,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/auto/dry-run-once').replace(
      queryParameters: {'gate_level': gateLevel.toString()},
    );
    final r = await _client.post(
      uri,
      headers: const {'Content-Type': 'application/json'},
      body: jsonEncode(const {}),
    );
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid backend response.');
    }
    return KisAutoSimulatorResult.fromJson(Map<String, dynamic>.from(decoded));
  }

  Future<KisSchedulerSimulationStatus> fetchKisSchedulerStatus() async {
    final payload = await _getJsonNoCache('/kis/scheduler/status');
    return KisSchedulerSimulationStatus.fromJson(payload);
  }

  Future<KisSchedulerReadiness> fetchKisSchedulerReadiness({
    bool includeModules = true,
    bool includeRecentRuns = true,
    bool includeRaw = false,
  }) async {
    final query = Uri(queryParameters: {
      'include_modules': includeModules.toString(),
      'include_recent_runs': includeRecentRuns.toString(),
      if (includeRaw) 'include_raw': 'true',
    }).query;
    final payload = await _getJsonNoCache('/kis/scheduler/readiness?$query');
    return KisSchedulerReadiness.fromJson(payload);
  }

  Future<KisSchedulerDryRunOrchestration>
      runKisSchedulerDryRunOrchestrationOnce({
    String? slotLabel,
    bool includeBuy = true,
    bool includeSell = true,
    bool includeRaw = false,
  }) async {
    final body = <String, dynamic>{
      if (slotLabel != null) 'slot_label': slotLabel,
      'include_buy': includeBuy,
      'include_sell': includeSell,
      'include_raw': includeRaw,
    };
    final payload = await _postJsonBody(
      '/kis/scheduler/run-dry-run-orchestration-once',
      body,
    );
    return KisSchedulerDryRunOrchestration.fromJson(payload);
  }

  Future<KisSchedulerDryRunReview> fetchKisSchedulerDryRunReview({
    int limit = 20,
    int days = 30,
    bool includeRaw = false,
    String? slotLabel,
    String? module,
  }) async {
    final query = Uri(queryParameters: {
      'limit': limit.toString(),
      'days': days.toString(),
      if (includeRaw) 'include_raw': 'true',
      if (slotLabel != null && slotLabel.trim().isNotEmpty)
        'slot_label': slotLabel.trim(),
      if (module != null && module.trim().isNotEmpty) 'module': module.trim(),
    }).query;
    final payload =
        await _getJsonNoCache('/kis/scheduler/dry-run-review?$query');
    return KisSchedulerDryRunReview.fromJson(payload);
  }

  Future<KisSchedulerRunResult> runKisSchedulerDryRunOnce() async {
    final payload =
        await _postJsonBody('/kis/scheduler/run-dry-run-auto-once', const {});
    return KisSchedulerRunResult.fromJson(payload);
  }

  Future<KisAutoReadiness> fetchKisAutoReadiness() async {
    final payload = await _getJsonNoCache('/kis/auto/readiness');
    return KisAutoReadiness.fromJson(payload);
  }

  Future<KisAutoReadiness> runKisAutoPreflightOnce() async {
    final payload = await _postJsonBody('/kis/auto/preflight-once', const {});
    return KisAutoReadiness.fromJson(payload);
  }

  static PositionSummary _normalizeKrPositionSummary(PositionSummary position) {
    final costBasis = position.costBasis > 0
        ? position.costBasis
        : position.qty > 0 && position.avgEntryPrice > 0
            ? position.qty * position.avgEntryPrice
            : 0.0;
    final marketValue = position.marketValue > 0
        ? position.marketValue
        : position.qty > 0 &&
                position.currentPrice != null &&
                position.currentPrice! > 0
            ? position.qty * position.currentPrice!
            : 0.0;
    final unrealizedPl = position.unrealizedPl != 0
        ? position.unrealizedPl
        : costBasis > 0 && marketValue > 0
            ? marketValue - costBasis
            : 0.0;
    final unrealizedPlpc = costBasis > 0 ? unrealizedPl / costBasis : 0.0;

    return PositionSummary(
      symbol: position.symbol,
      name: position.name,
      side: position.side,
      qty: position.qty,
      avgEntryPrice: position.avgEntryPrice,
      costBasis: costBasis,
      currentPrice: position.currentPrice,
      marketValue: marketValue,
      unrealizedPl: unrealizedPl,
      unrealizedPlpc: unrealizedPlpc,
    );
  }

  Future<KisLiveExitPreflightResult> runKisLiveExitPreflight() async {
    final payload =
        await _postJsonBody('/kis/live-exit/preflight-once', const {});
    return KisLiveExitPreflightResult.fromJson(payload);
  }

  Future<KisExitShadowDecision> runKisExitShadowOnce() async {
    final payload = await _postJsonBody('/kis/exit-shadow/run-once', const {});
    return KisExitShadowDecision.fromJson(payload);
  }

  Future<KisShadowExitReview> fetchKisShadowExitReview({
    int days = 30,
    int limit = 20,
    String? symbol,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/exit-shadow/review')
        .replace(queryParameters: {
      'days': days.toString(),
      'limit': limit.toString(),
      if (symbol != null && symbol.trim().isNotEmpty) 'symbol': symbol.trim(),
      '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
    });
    final r = await _client.get(uri, headers: const {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    });
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException('Invalid KIS shadow review response.');
    }
    return KisShadowExitReview.fromJson(Map<String, dynamic>.from(decoded));
  }

  Future<KisShadowExitReviewQueue> fetchKisShadowExitReviewQueue({
    int days = 30,
    int limit = 50,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/kis/exit-shadow/review-queue')
        .replace(queryParameters: {
      'days': days.toString(),
      'limit': limit.toString(),
      '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
    });
    final r = await _client.get(uri, headers: const {
      'Cache-Control': 'no-cache',
      'Pragma': 'no-cache',
    });
    if (r.statusCode >= 400) {
      throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
    }
    final decoded = jsonDecode(r.body);
    if (decoded is! Map) {
      throw const ApiRequestException(
          'Invalid KIS shadow review queue response.');
    }
    return KisShadowExitReviewQueue.fromJson(
        Map<String, dynamic>.from(decoded));
  }

  Future<KisShadowExitReviewQueueAction> markKisShadowExitQueueItemReviewed(
    String queueId, {
    String? note,
  }) async {
    final encodedQueueId = Uri.encodeComponent(queueId);
    final payload = await _postJsonBody(
      '/kis/exit-shadow/review-queue/$encodedQueueId/mark-reviewed',
      {
        if (note != null && note.trim().isNotEmpty)
          'operator_note': note.trim(),
      },
    );
    return KisShadowExitReviewQueueAction.fromJson(payload);
  }

  Future<KisShadowExitReviewQueueAction> dismissKisShadowExitQueueItem(
    String queueId, {
    String? note,
  }) async {
    final encodedQueueId = Uri.encodeComponent(queueId);
    final payload = await _postJsonBody(
      '/kis/exit-shadow/review-queue/$encodedQueueId/dismiss',
      {
        if (note != null && note.trim().isNotEmpty)
          'operator_note': note.trim(),
      },
    );
    return KisShadowExitReviewQueueAction.fromJson(payload);
  }

  Future<KisLimitedAutoSell> runKisLimitedAutoSellOnce() async {
    final payload =
        await _postJsonBody('/kis/limited-auto-sell/run-once', const {});
    return KisLimitedAutoSell.fromJson(payload);
  }

  Future<KisLimitedAutoSell> fetchKisLimitedAutoSellStatus() async {
    final payload = await _getJsonNoCache('/kis/limited-auto-sell/status');
    return KisLimitedAutoSell.fromJson(payload);
  }

  Future<KisLimitedAutoSell> runKisLimitedAutoSellPreflightOnce() async {
    final payload = await _postJsonBody(
      '/kis/limited-auto-sell/preflight-once',
      const {},
    );
    return KisLimitedAutoSell.fromJson(payload);
  }

  Future<KisBuyShadowDecision> runKisBuyShadowOnce() async {
    final payload = await _postJsonBody('/kis/buy-shadow/run-once', const {});
    return KisBuyShadowDecision.fromJson(payload);
  }

  Future<KisLimitedAutoBuy> fetchKisLimitedAutoBuyStatus({
    int? gateLevel,
  }) async {
    final path = gateLevel == null
        ? '/kis/limited-auto-buy/status'
        : '/kis/limited-auto-buy/status?gate_level=$gateLevel';
    final payload = await _getJsonNoCache(path);
    return KisLimitedAutoBuy.fromJson(payload);
  }

  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyPreflightOnce({
    int? gateLevel,
  }) async {
    final path = gateLevel == null
        ? '/kis/limited-auto-buy/preflight-once'
        : '/kis/limited-auto-buy/preflight-once?gate_level=$gateLevel';
    final payload = await _postJsonBody(path, const {});
    return KisLimitedAutoBuy.fromJson(payload);
  }

  Future<KisLimitedAutoBuy> runKisLimitedAutoBuyOnce({int? gateLevel}) async {
    final path = gateLevel == null
        ? '/kis/limited-auto-buy/run-once'
        : '/kis/limited-auto-buy/run-once?gate_level=$gateLevel';
    final payload = await _postJsonBody(path, const {});
    return KisLimitedAutoBuy.fromJson(payload);
  }

  Future<KisLimitedAutoBuyReview> fetchKisLimitedAutoBuyReview({
    int limit = 20,
    int days = 30,
    String? symbol,
    bool includeRaw = false,
  }) async {
    final query = Uri(queryParameters: {
      'limit': limit.toString(),
      'days': days.toString(),
      if (symbol != null && symbol.trim().isNotEmpty) 'symbol': symbol.trim(),
      if (includeRaw) 'include_raw': 'true',
    }).query;
    final payload =
        await _getJsonNoCache('/kis/limited-auto-buy/review?$query');
    return KisLimitedAutoBuyReview.fromJson(payload);
  }

  Future<KisLimitedAutoBuyExecutionReview>
      fetchKisLimitedAutoBuyExecutionReview({
    int limit = 20,
    int days = 30,
    String? symbol,
    bool includeRaw = false,
  }) async {
    final query = Uri(queryParameters: {
      'limit': limit.toString(),
      'days': days.toString(),
      if (symbol != null && symbol.trim().isNotEmpty) 'symbol': symbol.trim(),
      if (includeRaw) 'include_raw': 'true',
    }).query;
    final payload = await _getJsonNoCache(
      '/kis/limited-auto-buy/execution-review?$query',
    );
    return KisLimitedAutoBuyExecutionReview.fromJson(payload);
  }

  Future<KisSingleSymbolTradingResult> runKisSingleSymbolAnalyzeBuy({
    required String symbol,
    int? gateLevel,
    int? quantity,
    double? amount,
    required bool confirmLive,
    bool? dryRun,
    String requestedAction = 'analyze_then_maybe_buy',
    String sourceEndpoint = 'flutter_trading',
    Map<String, dynamic>? sourceContext,
  }) async {
    final body = {
      'symbol': symbol.trim(),
      if (gateLevel != null) 'gate_level': gateLevel,
      if (quantity != null) 'quantity': quantity,
      if (amount != null) 'amount': amount,
      'confirm_live': confirmLive,
      if (dryRun != null) 'dry_run': dryRun,
      'requested_action': requestedAction,
      'source_endpoint': sourceEndpoint,
      if (sourceContext != null && sourceContext.isNotEmpty)
        'source_context': sourceContext,
      'trigger_source': 'manual_kis_single_symbol',
      'mode': 'kis_single_symbol_analyze_buy',
    };
    final payload = await _postJsonBody('/kis/trading/run-once', body);
    return KisSingleSymbolTradingResult.fromJson(payload);
  }

  Future<KisSchedulerLiveResult> runKisSchedulerLiveOnce() async {
    final payload =
        await _postJsonBody('/kis/scheduler/run-live-once', const {});
    return KisSchedulerLiveResult.fromJson(payload);
  }

  Future<KisSchedulerGuardedSellResult>
      fetchKisSchedulerGuardedSellStatus() async {
    final payload = await _getJsonNoCache('/kis/scheduler/guarded-sell/status');
    return KisSchedulerGuardedSellResult.fromJson(payload);
  }

  Future<KisSchedulerGuardedSellResult> runKisSchedulerGuardedSellOnce({
    String? slotLabel,
    bool includeRaw = false,
    String triggerSource = 'scheduler_manual_test',
  }) async {
    final body = <String, dynamic>{
      if (slotLabel != null && slotLabel.trim().isNotEmpty)
        'slot_label': slotLabel.trim(),
      'include_raw': includeRaw,
      'trigger_source': triggerSource,
    };
    final payload = await _postJsonBody(
      '/kis/scheduler/run-guarded-sell-once',
      body,
    );
    return KisSchedulerGuardedSellResult.fromJson(payload);
  }

  Future<KisSchedulerGuardedSellReview> fetchKisSchedulerGuardedSellReview({
    int limit = 20,
    int days = 30,
    String? symbol,
    bool includeRaw = false,
    String? result,
  }) async {
    final query = Uri(queryParameters: {
      'limit': limit.toString(),
      'days': days.toString(),
      if (symbol != null && symbol.trim().isNotEmpty) 'symbol': symbol.trim(),
      if (includeRaw) 'include_raw': 'true',
      if (result != null && result.trim().isNotEmpty) 'result': result.trim(),
    }).query;
    final payload =
        await _getJsonNoCache('/kis/scheduler/guarded-sell/review?$query');
    return KisSchedulerGuardedSellReview.fromJson(payload);
  }

  Future<KisSchedulerGuardedBuyResult>
      fetchKisSchedulerGuardedBuyStatus() async {
    final payload = await _getJsonNoCache('/kis/scheduler/guarded-buy/status');
    return KisSchedulerGuardedBuyResult.fromJson(payload);
  }

  Future<KisSchedulerGuardedBuyResult> runKisSchedulerGuardedBuyOnce({
    String? slotLabel,
    bool includeRaw = false,
    String triggerSource = 'scheduler_manual_test',
  }) async {
    final body = <String, dynamic>{
      if (slotLabel != null && slotLabel.trim().isNotEmpty)
        'slot_label': slotLabel.trim(),
      'include_raw': includeRaw,
      'trigger_source': triggerSource,
    };
    final payload = await _postJsonBody(
      '/kis/scheduler/run-guarded-buy-once',
      body,
    );
    return KisSchedulerGuardedBuyResult.fromJson(payload);
  }

  Future<OpsProductionReadiness> fetchOpsProductionReadiness({
    bool includeRaw = false,
    int days = 7,
    bool includeRecent = true,
  }) async {
    final query = Uri(queryParameters: {
      'include_raw': includeRaw.toString(),
      'days': days.toString(),
      'include_recent': includeRecent.toString(),
    }).query;
    final payload = await _getJsonNoCache('/ops/production-readiness?$query');
    return OpsProductionReadiness.fromJson(payload);
  }

  Future<WatchlistRunResult> runWatchlistForProvider({
    required String provider,
    required int gateLevel,
  }) {
    final normalized = provider.trim().toLowerCase();
    if (normalized == 'kis') {
      return runKisWatchlistPreview(gateLevel: gateLevel);
    }
    return runWatchlistOnce();
  }

  Future<OpsSettings> getOpsSettings() async {
    try {
      final j = await _getJson('/ops/settings');
      final krNoNewEntryAfter = (j['kr_no_new_entry_after'] ??
              j['no_new_entry_after'] ??
              j['kis_limited_auto_buy_no_new_entry_after'] ??
              '14:50')
          .toString();
      final usNoNewEntryAfter =
          (j['us_no_new_entry_after'] ?? '15:45').toString();
      return OpsSettings(
        schedulerEnabled: j['scheduler_enabled'] == true,
        botEnabled: j['bot_enabled'] == true,
        dryRun: j['dry_run'] != false,
        killSwitch: j['kill_switch'] == true,
        brokerMode: (j['broker_mode'] ?? 'Paper').toString(),
        defaultGateLevel: _readInt(j['default_gate_level'], 2),
        maxDailyTrades:
            _readInt(j['max_daily_trades'] ?? j['max_trades_per_day'], 5),
        maxDailyEntries: _readInt(
            j['max_daily_entries'] ?? j['global_daily_entry_limit'], 2),
        minEntryScore: _readInt(j['min_entry_score'], 65),
        minScoreGap: _readInt(j['min_score_gap'], 3),
        currentOperationMode:
            (j['current_operation_mode'] ?? 'safe_mode').toString(),
        maxLiveOrdersPerDay: _readInt(
            j['max_live_orders_per_day'] ??
                j['kis_scheduler_max_live_orders_per_day'],
            1),
        maxPositions: _readInt(
            j['max_positions'] ??
                j['max_open_positions'] ??
                j['kis_limited_auto_buy_max_positions'],
            3),
        maxPositionPct: _readNullableDouble(j['max_position_pct']) ?? 0.03,
        maxOrderNotionalPct:
            _readNullableDouble(j['max_order_notional_pct']) ?? 0.03,
        dailyMaxLossPct: _readNullableDouble(j['daily_max_loss_pct']) ?? 0,
        noNewEntryAfter: krNoNewEntryAfter,
        krNoNewEntryAfter: krNoNewEntryAfter,
        usNoNewEntryAfter: usNoNewEntryAfter,
        usNoNewEntryAfterReadOnly:
            j['us_no_new_entry_after_read_only'] != false,
        usNoNewEntryAfterDerived: j['us_no_new_entry_after_derived'] != false,
        stopLossPct: _readNullableDouble(j['stop_loss_pct']) ?? 0.015,
        takeProfitPct: _readNullableDouble(j['take_profit_pct']) ?? 0.03,
        kisLiveAutoEnabled: j['kis_live_auto_enabled'] == true,
        kisLiveAutoBuyEnabled: j['kis_live_auto_buy_enabled'] == true,
        kisLiveAutoSellEnabled: j['kis_live_auto_sell_enabled'] == true,
        kisLiveAutoRequiresManualConfirm:
            j['kis_live_auto_requires_manual_confirm'] != false,
        kisLiveAutoMaxOrdersPerDay:
            _readInt(j['kis_live_auto_max_orders_per_day'], 1),
        kisLiveAutoMaxNotionalPct:
            _readNullableDouble(j['kis_live_auto_max_notional_pct']) ?? 0.03,
        kisLimitedAutoSellEnabled: j['kis_limited_auto_sell_enabled'] == true,
        kisLimitedAutoStopLossEnabled:
            j['kis_limited_auto_stop_loss_enabled'] == true ||
                j['kis_limited_auto_sell_stop_loss_enabled'] == true,
        kisLimitedAutoTakeProfitEnabled:
            j['kis_limited_auto_take_profit_enabled'] == true ||
                j['kis_limited_auto_sell_take_profit_enabled'] == true,
        kisLimitedAutoSellStopLossEnabled:
            j['kis_limited_auto_stop_loss_enabled'] == true ||
                j['kis_limited_auto_sell_stop_loss_enabled'] == true,
        kisLimitedAutoSellTakeProfitEnabled:
            j['kis_limited_auto_take_profit_enabled'] == true ||
                j['kis_limited_auto_sell_take_profit_enabled'] == true,
        kisLimitedAutoSellRequiresQueueReview:
            j['kis_limited_auto_sell_requires_queue_review'] != false,
        kisLimitedAutoSellMaxOrdersPerDay:
            _readInt(j['kis_limited_auto_sell_max_orders_per_day'], 1),
        kisLimitedAutoSellMaxNotionalPct:
            _readNullableDouble(j['kis_limited_auto_sell_max_notional_pct']) ??
                0.03,
        kisLimitedAutoSellMinShadowOccurrences:
            _readInt(j['kis_limited_auto_sell_min_shadow_occurrences'], 1),
        kisLimitedAutoSellAllowManualReviewTrigger:
            j['kis_limited_auto_sell_allow_manual_review_trigger'] == true,
        kisLimitedAutoSellAllowTakeProfitTrigger:
            j['kis_limited_auto_sell_allow_take_profit_trigger'] == true,
        kisLimitedAutoBuyEnabled: j['kis_limited_auto_buy_enabled'] == true,
        kisLimitedAutoBuyReadinessEnabled:
            j['kis_limited_auto_buy_readiness_enabled'] != false,
        kisLimitedAutoBuyShadowEnabled:
            j['kis_limited_auto_buy_shadow_enabled'] != false,
        kisLimitedAutoBuyRequiresShadowReview:
            j['kis_limited_auto_buy_requires_shadow_review'] != false,
        kisLimitedAutoBuyMaxOrdersPerDay:
            _readInt(j['kis_limited_auto_buy_max_orders_per_day'], 1),
        kisLimitedAutoBuyMaxNotionalPct:
            _readNullableDouble(j['kis_limited_auto_buy_max_notional_pct']) ??
                0.03,
        kisLimitedAutoBuyMinCashBufferKrw: _readNullableDouble(
                j['kis_limited_auto_buy_min_cash_buffer_krw']) ??
            0,
        kisLimitedAutoBuyRequiresExistingSellGuards:
            j['kis_limited_auto_buy_requires_existing_sell_guards'] != false,
        kisLimitedAutoBuyMinFinalScore:
            _readNullableDouble(j['kis_limited_auto_buy_min_final_score']) ??
                75,
        kisLimitedAutoBuyMinConfidence:
            _readNullableDouble(j['kis_limited_auto_buy_min_confidence']) ??
                0.70,
        kisLimitedAutoBuyMaxPositions:
            _readInt(j['kis_limited_auto_buy_max_positions'], 3),
        kisLimitedAutoBuyBlockIfPositionExists:
            j['kis_limited_auto_buy_block_if_position_exists'] != false,
        kisLimitedAutoBuyBlockIfOpenOrderExists:
            j['kis_limited_auto_buy_block_if_open_order_exists'] != false,
        kisLimitedAutoBuyAllowReentrySameDay:
            j['kis_limited_auto_buy_allow_reentry_same_day'] == true,
        kisLimitedAutoBuyRequireMarketOpen:
            j['kis_limited_auto_buy_require_market_open'] != false,
        kisLimitedAutoBuyNoNewEntryAfter:
            (j['kis_limited_auto_buy_no_new_entry_after'] ?? krNoNewEntryAfter)
                .toString(),
        kisLimitedAutoBuyAllowGptHardBlock:
            j['kis_limited_auto_buy_allow_gpt_hard_block'] == true,
        kisSchedulerEnabled: j['kis_scheduler_enabled'] == true,
        kisSchedulerDryRun: j['kis_scheduler_dry_run'] != false,
        kisSchedulerLiveEnabled: j['kis_scheduler_live_enabled'] == true,
        kisSchedulerAllowRealOrders:
            j['kis_scheduler_allow_real_orders'] == true,
        kisSchedulerConfiguredAllowRealOrders:
            j['kis_scheduler_configured_allow_real_orders'] == true,
        kisSchedulerBuyEnabled: j['kis_scheduler_buy_enabled'] == true,
        kisSchedulerSellEnabled: j['kis_scheduler_sell_enabled'] == true,
        kisSchedulerAllowLimitedAutoBuy:
            j['kis_scheduler_allow_limited_auto_buy'] == true,
        kisSchedulerAllowLimitedAutoSell:
            j['kis_scheduler_allow_limited_auto_sell'] == true,
        kisSchedulerMaxLiveOrdersPerDay:
            _readInt(j['kis_scheduler_max_live_orders_per_day'], 1),
        kisSchedulerLiveRequiresDryRunFalse:
            j['kis_scheduler_live_requires_dry_run_false'] != false,
        kisSchedulerLiveRespectKillSwitch:
            j['kis_scheduler_live_respect_kill_switch'] != false,
      );
    } catch (_) {
      return const OpsSettings(
        schedulerEnabled: false,
        botEnabled: false,
        dryRun: true,
        killSwitch: false,
        brokerMode: 'Paper',
        defaultGateLevel: 2,
        maxDailyTrades: 5,
        maxDailyEntries: 2,
        minEntryScore: 65,
        minScoreGap: 3,
      );
    }
  }

  Future<void> updateOpsSettings(Map<String, dynamic> values) async {
    await _putJsonBody('/ops/settings', values);
  }

  Future<Map<String, dynamic>> applyOpsSettingsPreset({
    required String preset,
    bool confirmDangerous = false,
  }) async {
    return _postJsonBody('/ops/settings/apply-preset', {
      'preset': preset,
      'confirm_dangerous': confirmDangerous,
    });
  }

  Future<SchedulerStatus> fetchSchedulerStatus() async {
    final payload = await _getJsonNoCache('/scheduler/status');
    return SchedulerStatus.fromJson(payload);
  }

  Future<void> schedulerOn() => _post('/ops/scheduler/on');
  Future<void> schedulerOff() => _post('/ops/scheduler/off');
  Future<void> botOn() => _post('/ops/bot/on');
  Future<void> botOff() => _post('/ops/bot/off');
  Future<void> killSwitchOn() => _post('/ops/kill-switch/on');
  Future<void> killSwitchOff() => _post('/ops/kill-switch/off');
  Future<WatchlistRunResult> runWatchlistOnce() async {
    final j = await _postJson('/trading/run-watchlist-once');
    return WatchlistRunResult.fromJson(j);
  }

  Future<WatchlistRunResult?> fetchLatestWatchlistRunResult() async {
    final uri = Uri.parse('${AppConfig.baseUrl}/trading/watchlist/latest')
        .replace(queryParameters: {
      '_ts': DateTime.now().millisecondsSinceEpoch.toString(),
    });

    try {
      final r = await _client.get(uri, headers: const {
        'Cache-Control': 'no-cache',
        'Pragma': 'no-cache',
      });
      if (r.statusCode == 404 || r.statusCode == 204) return null;
      if (r.statusCode >= 400) {
        throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
      }

      final decoded = jsonDecode(r.body);
      if (decoded is! Map) {
        throw const ApiRequestException('Invalid latest run response.');
      }

      final body = Map<String, dynamic>.from(decoded);
      final rawItem = body.containsKey('item') ? body['item'] : body;
      if (body['has_data'] == false || rawItem == null) return null;
      if (rawItem is! Map) {
        throw const ApiRequestException('Invalid latest run item.');
      }

      return WatchlistRunResult.fromJson(Map<String, dynamic>.from(rawItem));
    } on ApiRequestException {
      rethrow;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend response: $e');
    } on http.ClientException {
      throw const ApiRequestException(
          'Backend unreachable. Check API_BASE_URL and server status.');
    } catch (e) {
      throw ApiRequestException('Latest watchlist run unavailable: $e');
    }
  }

  Future<ManualTradingRunResult> runTradingOnce({
    required String symbol,
    required int gateLevel,
  }) async {
    final uri = Uri.parse('${AppConfig.baseUrl}/trading/run-once').replace(
      queryParameters: {
        'symbol': symbol.trim().toUpperCase(),
        'gate_level': gateLevel.toString(),
        'trigger_source': 'manual',
      },
    );

    try {
      final r = await _client.post(uri);
      if (r.statusCode == 404) {
        throw const ApiRequestException(
            'Manual trading endpoint is not available on this backend.');
      }
      if (r.statusCode == 422) {
        throw ApiRequestException('Validation failed: ${r.body}');
      }
      if (r.statusCode >= 400) {
        throw ApiRequestException('HTTP ${r.statusCode}: ${r.body}');
      }
      return ManualTradingRunResult.fromJson(
          jsonDecode(r.body) as Map<String, dynamic>);
    } on ApiRequestException {
      rethrow;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend response: $e');
    } on http.ClientException {
      throw const ApiRequestException(
          'Backend unreachable. Check API_BASE_URL and server status.');
    } catch (_) {
      throw const ApiRequestException(
          'Backend unreachable. Check API_BASE_URL and server status.');
    }
  }

  Future<List<TradingRun>> getRecentTradingRuns() async {
    try {
      final runs = await fetchRecentRuns(limit: 50);
      return runs.map((e) {
        return TradingRun(
          timestamp: e.createdAt,
          triggerSource: e.triggerSource,
          symbol: e.symbol,
          result: e.result,
          reason: e.reason,
          bestScore: 0,
          orderId: e.relatedOrderId,
          action: e.action,
          gateLevel: e.gateLevel,
        );
      }).toList();
    } catch (_) {
      return mockRuns;
    }
  }

  Future<List<TradingLogItem>> fetchRecentRuns({int limit = 20}) async {
    try {
      final j = await _getJson('/runs/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map>()
          .map((item) =>
              TradingLogItem.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    } on http.ClientException {
      return mockTradingLogs;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend logs response: $e');
    }
  }

  Future<List<OrderLogItem>> fetchRecentOrders({int limit = 20}) async {
    try {
      final j = await _getJson('/orders/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map>()
          .map((item) => OrderLogItem.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    } on http.ClientException {
      return mockOrderLogs;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend orders response: $e');
    }
  }

  Future<List<SignalLogItem>> fetchRecentSignals({int limit = 20}) async {
    try {
      final j = await _getJson('/signals/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map>()
          .map(
              (item) => SignalLogItem.fromJson(Map<String, dynamic>.from(item)))
          .toList();
    } on http.ClientException {
      return mockSignalLogs;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend signals response: $e');
    }
  }

  Future<List<Map<String, dynamic>>> fetchRecentSignalPayloads({
    int limit = 20,
  }) async {
    try {
      final j = await _getJson('/signals/recent?limit=$limit');
      final items = j['items'] as List<dynamic>? ?? [];
      return items
          .whereType<Map>()
          .map((item) => Map<String, dynamic>.from(item))
          .toList();
    } on http.ClientException {
      return const [];
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend signals response: $e');
    }
  }

  Future<LogsSummary> fetchLogsSummary() async {
    try {
      final j = await _getJson('/logs/summary');
      return LogsSummary.fromJson(j);
    } on http.ClientException {
      return mockLogsSummary;
    } on FormatException catch (e) {
      throw ApiRequestException('Invalid backend logs summary: $e');
    }
  }

  WatchlistRunResult getMockRunResult() {
    return const WatchlistRunResult(
      configuredSymbolCount: 50,
      analyzedSymbolCount: 50,
      quantCandidatesCount: 5,
      researchedCandidatesCount: 5,
      finalBestCandidate: 'WMT',
      secondFinalCandidate: 'CSCO',
      tiedFinalCandidates: ['WMT', 'CSCO', 'APP'],
      nearTiedCandidates: ['WMT', 'CSCO', 'APP'],
      tieBreakerApplied: true,
      finalCandidateSelectionReason:
          'Tie-breaker prioritized stability and volume momentum among near-tied final candidates.',
      bestScore: 68,
      finalScoreGap: 0,
      minEntryScore: 65,
      minScoreGap: 3,
      shouldTrade: false,
      triggeredSymbol: null,
      triggerBlockReason: 'weak_final_score_gap',
      finalEntryReady: false,
      finalActionHint: 'watch',
      action: 'hold',
      orderId: null,
      topQuantCandidates: [
        Candidate(
            symbol: 'WMT',
            score: 68,
            note: 'Low drawdown',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'CSCO',
            score: 68,
            note: 'Stable trend',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'APP',
            score: 68,
            note: 'Momentum',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap')
      ],
      researchedCandidates: [
        Candidate(
            symbol: 'WMT',
            score: 68,
            note: 'Defensive retail signal',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'CSCO',
            score: 67,
            note: 'Earnings resilience',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'APP',
            score: 67,
            note: 'AI demand',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap')
      ],
      finalRankedCandidates: [
        Candidate(
            symbol: 'WMT',
            score: 68,
            note: 'Selected after tie-breaker',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'CSCO',
            score: 68,
            note: 'Near tied',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap'),
        Candidate(
            symbol: 'APP',
            score: 68,
            note: 'Near tied',
            entryReady: false,
            actionHint: 'watch',
            blockReason: 'weak_final_score_gap')
      ],
      result: 'skipped',
      reason: 'weak_final_score_gap',
      triggerSource: 'manual',
    );
  }
}

class _KrPortfolioEndpointResult {
  const _KrPortfolioEndpointResult._({this.payload, this.error});

  factory _KrPortfolioEndpointResult.success(Map<String, dynamic> payload) =>
      _KrPortfolioEndpointResult._(payload: payload);

  factory _KrPortfolioEndpointResult.failure(ApiRequestException error) =>
      _KrPortfolioEndpointResult._(error: error);

  final Map<String, dynamic>? payload;
  final ApiRequestException? error;
}

class _KrPortfolioAuthDetails {
  const _KrPortfolioAuthDetails({
    this.message,
    this.nextRefreshAllowedAt,
    this.tokenExpired = false,
  });

  final String? message;
  final String? nextRefreshAllowedAt;
  final bool tokenExpired;
}

ApiRequestException _apiRequestExceptionFromResponse(http.Response response) {
  final detail = _apiErrorDetailFromBody(response.body);
  return ApiRequestException(
    'HTTP ${response.statusCode}: ${response.body}',
    statusCode: response.statusCode,
    detail: detail,
  );
}

Map<String, dynamic> _apiErrorDetailFromMessage(String message) {
  final marker = RegExp(r'^HTTP\s+\d+:\s*');
  final body = message.replaceFirst(marker, '');
  return _apiErrorDetailFromBody(body);
}

Map<String, dynamic> _apiErrorDetailFromBody(String body) {
  final result = <String, dynamic>{};
  try {
    final decoded = jsonDecode(body);
    if (decoded is! Map) return result;
    final root = Map<String, dynamic>.from(decoded);
    final detail = root['detail'];
    if (detail is Map) {
      final detailMap = Map<String, dynamic>.from(detail);
      _copyKnownKisErrorFields(result, detailMap);
      final nested = detailMap['details'];
      if (nested is Map) {
        _copyKnownKisErrorFields(result, Map<String, dynamic>.from(nested));
      }
    } else if (detail is String) {
      result['msg1'] = detail;
    }
    _copyKnownKisErrorFields(result, root);
  } catch (_) {
    return result;
  }
  return result;
}

void _copyKnownKisErrorFields(
  Map<String, dynamic> target,
  Map<String, dynamic> source,
) {
  const keys = [
    'msg_cd',
    'msg1',
    'rt_cd',
    'token_expired',
    'refresh_guard_reason',
    'next_refresh_allowed_at',
    'refresh_attempted',
    'refresh_guard_bypassed_for_token_expired',
    'retry_failed',
  ];
  for (final key in keys) {
    final value = source[key];
    if (value != null && target[key] == null) target[key] = value;
  }
}

Map<String, dynamic> _safeKisAuditSourceMetadata(
    Map<String, dynamic>? sourceMetadata) {
  if (sourceMetadata == null) return const <String, dynamic>{};
  final source = sourceMetadata['source'];
  final isExitPreflight = source == 'kis_live_exit_preflight';
  final isExitShadow = source == 'kis_exit_shadow_decision';
  final isPortfolioManualSell = source == 'kis_portfolio_manual_sell';
  final isWatchlistPrefill = source == 'watchlist_candidate';
  final isDirectManualTicket = source == 'single_symbol_trading';
  final isAgentPlanPrefill = source == 'agent_plan';
  if (!isExitPreflight &&
      !isExitShadow &&
      !isPortfolioManualSell &&
      !isWatchlistPrefill &&
      !isDirectManualTicket &&
      !isAgentPlanPrefill) {
    return const <String, dynamic>{};
  }

  final result = <String, dynamic>{};
  const stringKeys = {
    'source',
    'source_type',
    'source_context',
    'operator_action_source',
    'market',
    'broker',
    'preflight_id',
    'preflight_run_key',
    'preflight_checked_at',
    'shadow_decision_run_key',
    'shadow_decision_checked_at',
    'checked_at',
    'exit_trigger',
    'trigger_source',
    'symbol',
    'company_name',
    'exit_reason',
    'action_hint',
    'block_reason',
    'candidate_reason',
    'candidate_action_hint',
    'candidate_block_reason',
    'agent_plan_key',
    'command_type',
    'domain',
    'plan_status',
    'scope_hash',
    'auth_type',
    'auth_status',
  };
  const numberKeys = {
    'gate_level',
    'score',
    'candidate_rank',
    'candidate_score',
    'unrealized_pl',
    'unrealized_pl_pct',
    'cost_basis',
    'current_value',
    'current_price',
    'suggested_quantity',
    'quantity',
    'estimated_amount',
    'agent_plan_id',
    'command_log_id',
    'auth_approval_request_id',
    'notional',
  };
  const boolKeys = {
    'manual_confirm_required',
    'auto_buy_enabled',
    'auto_sell_enabled',
    'scheduler_real_order_enabled',
    'real_order_submit_allowed',
    'real_order_submitted',
    'broker_submit_called',
    'manual_submit_called',
    'preflight_real_order_submitted',
    'preflight_broker_submit_called',
    'preflight_manual_submit_called',
    'shadow_real_order_submitted',
    'shadow_broker_submit_called',
    'shadow_manual_submit_called',
    'entry_ready',
    'candidate_entry_ready',
    'watchlist_click_submits_order',
    'requires_auth',
    'requires_user_review',
    'requires_user_validation',
    'requires_confirm_live',
  };
  const listKeys = {'risk_flags', 'gating_notes'};

  for (final key in stringKeys) {
    final text = _auditString(sourceMetadata[key]);
    if (text != null) result[key] = text;
  }
  for (final key in numberKeys) {
    final number = _auditNumber(sourceMetadata[key]);
    if (number != null) result[key] = number;
  }
  for (final key in boolKeys) {
    final value = _auditBool(sourceMetadata[key]);
    if (value != null) result[key] = value;
  }
  for (final key in listKeys) {
    final values = _auditStringList(sourceMetadata[key]);
    if (values.isNotEmpty) result[key] = values;
  }
  for (final key in const {
    'trigger_flags',
    'position_snapshot',
    'runtime_safety_snapshot',
  }) {
    final value = sourceMetadata[key];
    if (value is Map) {
      result[key] = Map<String, dynamic>.from(value.cast<String, dynamic>());
    }
  }

  result['source'] = isPortfolioManualSell
      ? 'kis_portfolio_manual_sell'
      : isExitShadow
          ? 'kis_exit_shadow_decision'
          : isExitPreflight
              ? 'kis_live_exit_preflight'
              : isWatchlistPrefill
                  ? 'watchlist_candidate'
                  : isAgentPlanPrefill
                      ? 'agent_plan'
                      : 'single_symbol_trading';
  result['source_type'] = isPortfolioManualSell
      ? 'operator_confirmed_position_exit'
      : isExitShadow
          ? 'dry_run_sell_simulation'
          : isExitPreflight
              ? 'manual_confirm_exit'
              : isWatchlistPrefill
                  ? (_auditString(sourceMetadata['source_type']) ??
                      'manual_buy_ticket_prefill')
                  : isAgentPlanPrefill
                      ? 'agent_manual_ticket_prefill'
                      : 'manual_buy_ticket_prefill';
  result['source_context'] = isPortfolioManualSell
      ? 'audit_sell_manual_ticket'
      : isExitShadow
          ? 'shadow_exit_manual_sell'
          : isExitPreflight
              ? 'exit_preflight_manual_sell'
              : isWatchlistPrefill
                  ? 'watchlist_analyze_in_trading'
                  : isAgentPlanPrefill
                      ? 'agent_manual_prefill'
                      : 'direct_manual_ticket';
  result['operator_action_source'] = result['source_context'];
  result['manual_confirm_required'] = true;
  result['auto_buy_enabled'] = false;
  result['auto_sell_enabled'] = false;
  result['scheduler_real_order_enabled'] = false;
  result['real_order_submit_allowed'] = isPortfolioManualSell
      ? (_auditBool(sourceMetadata['real_order_submit_allowed']) ?? false)
      : false;
  result['real_order_submitted'] = false;
  result['broker_submit_called'] = false;
  result['manual_submit_called'] = false;
  if (isPortfolioManualSell) {
    return result;
  } else if (isExitShadow) {
    result['shadow_real_order_submitted'] = false;
    result['shadow_broker_submit_called'] = false;
    result['shadow_manual_submit_called'] = false;
  } else {
    result['preflight_real_order_submitted'] = false;
    result['preflight_broker_submit_called'] = false;
    result['preflight_manual_submit_called'] = false;
  }
  return result;
}

String? _auditString(Object? value) {
  final text = value?.toString().trim();
  if (text == null || text.isEmpty || text == 'null') return null;
  return text.length > 200 ? text.substring(0, 200) : text;
}

num? _auditNumber(Object? value) {
  if (value is num) return value;
  final text = value?.toString().trim().replaceAll(',', '');
  if (text == null || text.isEmpty || text == 'null') return null;
  return num.tryParse(text);
}

bool? _auditBool(Object? value) {
  if (value == null) return null;
  if (value is bool) return value;
  if (value is num) return value != 0;
  final text = value.toString().trim().toLowerCase();
  if (text == 'true' || text == '1' || text == 'yes') return true;
  if (text == 'false' || text == '0' || text == 'no') return false;
  return null;
}

List<String> _auditStringList(Object? value) {
  if (value is! List) return const [];
  return [
    for (final item in value)
      if (_auditString(item) != null) _auditString(item)!,
  ];
}

const mockRuns = <TradingRun>[
  TradingRun(
      timestamp: '2026-04-26T12:20:00Z',
      triggerSource: 'manual',
      symbol: 'WMT',
      result: 'skipped',
      reason: 'weak_final_score_gap',
      bestScore: 68,
      orderId: null,
      action: 'hold',
      gateLevel: 2),
  TradingRun(
      timestamp: '2026-04-26T09:00:00Z',
      triggerSource: 'scheduler',
      symbol: 'CSCO',
      result: 'skipped',
      reason: 'weak_final_score_gap',
      bestScore: 67,
      orderId: null,
      action: 'hold',
      gateLevel: 2),
];
