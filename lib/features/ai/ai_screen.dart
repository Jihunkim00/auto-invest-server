import 'package:flutter/material.dart';

import '../../core/i18n/app_language.dart';
import '../../core/i18n/app_strings.dart';
import '../../core/network/api_error_formatter.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/kr_symbol.dart';
import '../../core/utils/kr_stock_catalog.dart';
import '../../core/widgets/section_card.dart';
import '../../models/agent_chat_live_order_action.dart';
import '../../models/agent_chat_v2_response.dart';
import '../../models/automation_strategy_profile.dart';
import '../dashboard/dashboard_controller.dart';
import '../dashboard/widgets/agent_chat_live_order_confirmation_card.dart';

class AiScreen extends StatefulWidget {
  const AiScreen({super.key, required this.controller, this.onOpenAdmin});

  final DashboardController controller;
  final VoidCallback? onOpenAdmin;

  @override
  State<AiScreen> createState() => _AiScreenState();
}

class _AiScreenState extends State<AiScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final List<_AiEntry> _entries = [];
  bool _loading = false;
  String? _conversationKey;
  String? _error;

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final strings = widget.controller.strings;
    return Material(
      color: Colors.transparent,
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 14, 16, 4),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Icon(Icons.auto_awesome,
                          color: AppTheme.primaryAccent),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(strings.aiAssistant,
                                style:
                                    Theme.of(context).textTheme.headlineMedium),
                            const SizedBox(height: 4),
                            Text(
                              strings.agentAssistantSubtitle,
                              style: const TextStyle(
                                  color: Colors.white70, height: 1.35),
                            ),
                          ],
                        ),
                      ),
                      IconButton(
                        key: const ValueKey('ai-open-admin'),
                        tooltip: strings.adminTooltip,
                        onPressed: widget.onOpenAdmin,
                        icon: const Icon(Icons.admin_panel_settings_outlined),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  _SafetyBadge(strings.noAutoSubmit),
                  const SizedBox(height: 8),
                  Text(strings.analysisReadOnlyNotice,
                      style:
                          const TextStyle(color: Colors.white60, height: 1.35)),
                ],
              ),
            ),
            _QuickActions(onSelected: _quickAction, strings: strings),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: _ErrorCard(_error!),
              ),
            Expanded(
              child: ListView(
                key: const ValueKey('ai-v2-message-thread'),
                controller: _scroll,
                padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
                children: [
                  if (_entries.isEmpty) _WelcomeCard(strings: strings),
                  for (final entry in _entries)
                    _EntryView(
                      entry: entry,
                      strings: strings,
                      controller: widget.controller,
                      onConfirm: _confirm,
                      onCancel: _cancel,
                    ),
                  if (_loading)
                    Align(
                      alignment: Alignment.centerLeft,
                      child: Padding(
                        padding: EdgeInsets.all(8),
                        child: Text(strings.aiAnalyzing,
                            style:
                                const TextStyle(color: AppTheme.primaryAccent)),
                      ),
                    ),
                ],
              ),
            ),
            _InputBar(
              controller: _input,
              loading: _loading,
              onSubmit: _send,
              strings: strings,
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _quickAction(String text) async {
    _input.text = text;
    await _send();
  }

  Future<void> _send() async {
    final text = _input.text.trim();
    if (text.isEmpty || _loading) return;
    KrStockMatch? resolved;
    try {
      await KrStockCatalog.shared.load();
      resolved = KrStockCatalog.shared.resolve(text);
    } catch (_) {
      // Direct lookup is optional UI enrichment; never fall back to the
      // active automation watchlist as a catalog.
    }
    final requestText = resolved == null
        ? text
        : '$text\n(종목코드: ${resolved.symbol}, 종목명: ${resolved.name})';
    _input.clear();
    setState(() {
      _error = null;
      _loading = true;
      _entries.add(_AiEntry.user(text));
    });
    try {
      final localQuote = await _lookupKrQuote(text, resolved);
      if (localQuote != null) {
        if (!mounted) return;
        setState(() {
          _loading = false;
          _entries.add(_AiEntry.quote(localQuote));
        });
        return;
      }

      final localProfileAnswer = await _lookupAutomationProfile(text);
      if (localProfileAnswer != null) {
        if (!mounted) return;
        setState(() {
          _loading = false;
          _entries.add(_AiEntry.local(localProfileAnswer));
        });
        return;
      }
      final kis = widget.controller.selectedProvider == SelectedProvider.kis;
      final response = await widget.controller.apiClient.sendAgentChatV2Message(
        message: requestText,
        conversationKey: _conversationKey,
        context: {
          'default_market': kis ? 'KR' : 'US',
          'default_provider': kis ? 'kis' : 'alpaca',
          'source': 'flutter_ai_v2',
          if (resolved != null) 'resolved_symbol': resolved.symbol,
          if (resolved != null) 'resolved_symbol_name': resolved.name,
        },
        language: widget.controller.appLanguage.code,
        locale: widget.controller.appLanguage.localeCode,
      );
      _conversationKey = response.conversationKey ?? _conversationKey;
      if (!mounted) return;
      setState(() {
        _loading = false;
        _entries.add(_AiEntry.assistant(response));
      });
      await Future<void>.delayed(const Duration(milliseconds: 30));
      if (_scroll.hasClients) {
        await _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOut,
        );
      }
    } catch (error) {
      if (!mounted) return;
      final message = _formatError(error);
      setState(() {
        _loading = false;
        _error = message;
        _entries.add(_AiEntry.error(message));
      });
    }
  }

  Future<_LocalQuote?> _lookupKrQuote(
    String text,
    KrStockMatch? resolved,
  ) async {
    if (resolved == null || !_isClearKrQuoteIntent(text)) return null;
    try {
      final data = await widget.controller.apiClient
          .fetchKisMarketPrice(resolved.symbol);
      return _LocalQuote(
        symbol: resolved.symbol,
        name: _textValue(data['name']) ?? resolved.name,
        data: data,
      );
    } catch (error) {
      return _LocalQuote(
        symbol: resolved.symbol,
        name: resolved.name,
        error: _formatError(error),
      );
    }
  }

  bool _isClearKrQuoteIntent(String text) {
    final normalized = text.toLowerCase();
    const quoteWords = <String>[
      '\uD604\uC7AC\uAC00',
      '\uAC00\uACA9',
      '\uC8FC\uAC00',
      '\uC2DC\uC138',
      '\uC5BC\uB9C8',
      'quote',
      'price',
    ];
    const nonQuoteWords = <String>[
      '\uBD84\uC11D',
      '\uD310\uB2E8',
      '\uB9E4\uC218',
      '\uB9E4\uB3C4',
      '\uC8FC\uBB38',
      '\uC0AC\uC918',
      '\uC0AC\uACE0 \uC2F6',
      '\uD314\uC544',
      'buy',
      'sell',
      'order',
      'analy',
    ];
    return quoteWords.any(normalized.contains) &&
        !nonQuoteWords.any(normalized.contains);
  }

  String? _textValue(Object? value) {
    final text = value?.toString().trim();
    return text == null || text.isEmpty || text == 'null' ? null : text;
  }

  Future<String?> _lookupAutomationProfile(String text) async {
    final normalized = text.toLowerCase();
    final mentionsProfile = normalized.contains('프로필') ||
        normalized.contains('자동화 프로필') ||
        normalized.contains('automation profile') ||
        normalized.contains('automation');
    final asksReadOnly = normalized.contains('현재') ||
        normalized.contains('상태') ||
        normalized.contains('알려') ||
        normalized.contains('보여') ||
        normalized.contains('일정') ||
        normalized.contains('list') ||
        normalized.contains('status');
    if (!_isAutomationProfileQuery(text) &&
        (!mentionsProfile || !asksReadOnly)) {
      return null;
    }
    try {
      final result =
          await widget.controller.apiClient.fetchAutomationProfiles();
      return _formatAutomationProfileAnswer(result, text);
    } catch (error) {
      return '\uC790\uB3D9\uD654 \uD504\uB85C\uD544 \uC870\uD68C \uC2E4\uD328: ${_formatError(error)}';
    }
  }

  bool _isAutomationProfileQuery(String text) {
    final normalized = text.toLowerCase();
    const profileWords = <String>[
      '\uD504\uB85C\uD544',
      '\uC790\uB3D9\uD654',
      '\uC6B4\uC6A9\uD14C\uC2A4\uD2B8',
      'automation',
      'profile',
    ];
    const lookupWords = <String>[
      '\uD604\uC7AC',
      '\uC0C1\uD0DC',
      '\uC54C\uB824',
      '\uC870\uD68C',
      '\uC77C\uC815',
      '\uAE30\uAC04',
      '\uBB50\uC57C',
      'list',
      'status',
      'schedule',
    ];
    return profileWords.any(normalized.contains) &&
        lookupWords.any(normalized.contains);
  }

  String _formatAutomationProfileAnswer(
    AutomationStrategyProfileList result,
    String query,
  ) {
    final requested = query.toLowerCase();
    final profiles = result.profiles;
    final selected = result.selectedProfile ??
        result.activeProfile ??
        _firstActiveProfile(profiles);
    final statusOnly = requested.contains('상태') ||
        requested.contains('status') ||
        requested.contains('현재');
    final named = _findNamedProfile(profiles, requested);
    if (_looksLikeNamedProfileQuery(requested) && named == null) {
      return '\uD574\uB2F9 \uC774\uB984\uC758 \uC790\uB3D9\uD654 \uD504\uB85C\uD544\uC744 \uCC3E\uC9C0 \uBABB\uD588\uC2B5\uB2C8\uB2E4.';
    }
    final items = named != null
        ? <AutomationStrategyProfile>[named]
        : statusOnly && selected != null
            ? <AutomationStrategyProfile>[selected]
            : profiles;
    if (items.isEmpty) return '조회된 자동화 프로필이 없습니다.';
    final lines = <String>['자동화 프로필 조회 결과입니다.'];
    for (final profile in items) {
      final operation = profile.operation;
      final entry = profile.entry;
      final schedule = entry['analysis_times'];
      final scheduleText =
          schedule is List && schedule.isNotEmpty ? schedule.join(', ') : null;
      final dates = [
        operation['start_date']?.toString(),
        operation['end_date']?.toString(),
      ].where((value) => value?.trim().isNotEmpty == true).join(' ~ ');
      final details = <String>[
        '\uC2DC\uC7A5: ${profile.provider.toUpperCase()} / ${profile.market}',
        '상태: ${_profileStatusLabel(profile.status)}',
        if (dates.isNotEmpty) '운영 기간: $dates',
        if (scheduleText != null) '분석 시간: $scheduleText',
        '최대 보유: ${profile.maxOpenPositions}종목',
        if (entry['max_new_entries_per_day'] != null)
          '일일 진입 한도: ${entry['max_new_entries_per_day']}',
      ];
      lines.add('${profile.name}: ${details.join(' · ')}');
    }
    return lines.join('\n');
  }

  AutomationStrategyProfile? _firstActiveProfile(
    List<AutomationStrategyProfile> profiles,
  ) {
    for (final profile in profiles) {
      if (profile.enabled && profile.status.toLowerCase() == 'active') {
        return profile;
      }
    }
    return null;
  }

  AutomationStrategyProfile? _findNamedProfile(
    List<AutomationStrategyProfile> profiles,
    String query,
  ) {
    final compactQuery = _compactLookupText(query);
    for (final profile in profiles) {
      for (final value in [profile.name, profile.profileKey]) {
        final compactName = _compactLookupText(value);
        if (compactName.isNotEmpty && compactQuery.contains(compactName)) {
          return profile;
        }
      }
    }
    return null;
  }

  bool _looksLikeNamedProfileQuery(String query) {
    final compact = _compactLookupText(query);
    return (compact.contains('profile') ||
            compact.contains('\uD504\uB85C\uD544')) &&
        !compact.contains('automationprofile') &&
        !compact.contains('\uC790\uB3D9\uD654\uD504\uB85C\uD544') &&
        !compact.contains('status') &&
        !compact.contains('schedule') &&
        !compact.contains('\uC0C1\uD0DC') &&
        !compact.contains('\uC77C\uC815');
  }

  String _compactLookupText(String value) =>
      value.toLowerCase().replaceAll(RegExp(r'[\s\-_()./]'), '');

  String _profileStatusLabel(String status) {
    switch (status.toLowerCase()) {
      case 'active':
        return '활성';
      case 'paused':
        return '일시정지';
      case 'archived':
        return '보관';
      default:
        return '비활성';
    }
  }

  Future<void> _confirm(AgentChatLiveOrderAction action) async {
    final result = await widget.controller.confirmAgentChatLiveOrder(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(result.message)));
  }

  Future<void> _cancel(AgentChatLiveOrderAction action) async {
    final result = await widget.controller.cancelAgentChatLiveOrder(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(result.message)));
  }

  String _formatError(Object error) {
    final value = ApiErrorFormatter.format(error.toString()).toLowerCase();
    if (value.contains('kill_switch') || value.contains('kill switch')) {
      return widget.controller.strings.aiSafetyBlocked;
    }
    if (value.contains('dry_run') || value.contains('dry run')) {
      return widget.controller.strings.aiDryRun;
    }
    if (value.contains('open order')) {
      return widget.controller.strings.aiOpenOrder;
    }
    return widget.controller.strings.aiError;
  }
}

class _LocalQuote {
  const _LocalQuote({
    required this.symbol,
    required this.name,
    this.data = const <String, dynamic>{},
    this.error,
  });

  final String symbol;
  final String name;
  final Map<String, dynamic> data;
  final String? error;
}

class _AiEntry {
  const _AiEntry({
    this.userText,
    this.response,
    this.error,
    this.localText,
    this.localQuote,
  });

  const _AiEntry.user(String value) : this(userText: value);
  const _AiEntry.assistant(AgentChatV2Response value) : this(response: value);
  const _AiEntry.error(String value) : this(error: value);
  const _AiEntry.local(String value) : this(localText: value);
  const _AiEntry.quote(_LocalQuote value) : this(localQuote: value);

  final String? userText;
  final AgentChatV2Response? response;
  final String? error;
  final String? localText;
  final _LocalQuote? localQuote;
}

class _QuickActions extends StatelessWidget {
  const _QuickActions({required this.onSelected, required this.strings});

  final ValueChanged<String> onSelected;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    const actions = <String, String>{
      '현재가': '삼성전자 현재가 얼마야?',
      '종목 분석': '삼성전자 분석해줘',
      '내 자산': '내 포트폴리오 보여줘',
      '최근 판단': '최근 자동매매 판단 알려줘',
      '왜 안 샀어?': '왜 오늘 매수하지 않았어?',
    };
    final labels = <String, String>{
      actions.keys.elementAt(0): strings.quickQuote,
      actions.keys.elementAt(1): strings.quickAnalysis,
      actions.keys.elementAt(2): strings.quickPortfolio,
      actions.keys.elementAt(3): strings.quickDecision,
      actions.keys.elementAt(4): strings.quickWhyNoBuy,
    };
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 10, 16, 12),
      child: Wrap(
        spacing: 10,
        runSpacing: 10,
        children: [
          for (final item in actions.entries)
            SizedBox(
              height: 46,
              child: MouseRegion(
                cursor: SystemMouseCursors.click,
                child: OutlinedButton(
                  key: ValueKey('ai-quick-' + item.key),
                  style: OutlinedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 18),
                    foregroundColor: Colors.white,
                    backgroundColor: Colors.white.withValues(alpha: 0.07),
                    side: const BorderSide(color: Colors.white30),
                    textStyle: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                    shape: const StadiumBorder(),
                  ),
                  onPressed: () => onSelected(item.value),
                  child: Text(labels[item.key] ?? item.key),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard({required this.strings});

  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      key: ValueKey('ai-v2-welcome-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(strings.aiWelcomeTitle,
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          SizedBox(height: 8),
          Text(
            strings.aiWelcomeDescription,
            style: TextStyle(color: Colors.white70, height: 1.35),
          ),
        ],
      ),
    );
  }
}

class _EntryView extends StatelessWidget {
  const _EntryView({
    required this.entry,
    required this.strings,
    required this.controller,
    required this.onConfirm,
    required this.onCancel,
  });

  final _AiEntry entry;
  final AppStrings strings;
  final DashboardController controller;
  final Future<void> Function(AgentChatLiveOrderAction) onConfirm;
  final Future<void> Function(AgentChatLiveOrderAction) onCancel;

  @override
  Widget build(BuildContext context) {
    if (entry.userText != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Align(
          alignment: Alignment.centerRight,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: MediaQuery.sizeOf(context).width * 0.82,
            ),
            child: Container(
              key: const ValueKey('ai-v2-user-message'),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: AppTheme.primaryAccent.withValues(alpha: 0.16),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Text(entry.userText!, softWrap: true),
            ),
          ),
        ),
      );
    }
    if (entry.error != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: _ErrorCard(entry.error!),
      );
    }
    if (entry.localQuote != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: _LocalQuoteCard(
          quote: entry.localQuote!,
          controller: controller,
          strings: strings,
        ),
      );
    }
    if (entry.localText != null) {
      return Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: SectionCard(
          key: const ValueKey('ai-local-assistant-message'),
          child: Text(entry.localText!, style: const TextStyle(height: 1.4)),
        ),
      );
    }
    final response = entry.response!;
    final preview = response.orderPreview;
    final action =
        preview == null ? null : AgentChatLiveOrderAction.fromJson(preview);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SectionCard(
          key: const ValueKey('ai-v2-assistant-message'),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: 8,
                runSpacing: 8,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.auto_awesome,
                          size: 16, color: Colors.lightBlueAccent),
                      const SizedBox(width: 6),
                      Text(_label(response.intent),
                          style: const TextStyle(
                              color: Colors.lightBlueAccent,
                              fontWeight: FontWeight.w800)),
                    ],
                  ),
                  _SafetyBadge(_statusLabel(response.status)),
                ],
              ),
              const SizedBox(height: 8),
              Text(response.displayAnswer,
                  key: const ValueKey('ai-v2-response-message'),
                  style: const TextStyle(height: 1.35)),
            ],
          ),
        ),
        const SizedBox(height: 10),
        if (response.intent == 'quote')
          _QuoteCard(
            response,
            strings: strings,
            controller: controller,
          ),
        if (response.intent == 'analyze' ||
            response.intent == 'market_analysis')
          _AnalysisCard(
            response,
            strings: strings,
            controller: controller,
          ),
        if (response.intent == 'explain')
          _DecisionCard(response, strings: strings),
        if (response.intent == 'portfolio')
          _PortfolioCard(response, strings: strings),
        if (action != null && response.requiresConfirmation)
          AgentChatLiveOrderConfirmationCard(
            action: action,
            busy: false,
            onConfirm: onConfirm,
            onCancel: onCancel,
          ),
      ],
    );
  }

  String _statusLabel(String status) {
    switch (status) {
      case 'completed':
        return '완료';
      case 'confirmation_required':
        return '확인 필요';
      case 'blocked':
        return '안전 차단';
      case 'error':
        return '조회 실패';
      case 'needs_clarification':
        return '확인 필요';
      default:
        return '안내';
    }
  }

  String _label(String intent) {
    switch (intent) {
      case 'analyze':
        return '분석';
      case 'market_analysis':
        return '분석';
      case 'quote':
        return '현재가';
      case 'account':
        return '계좌';
      case 'affordability':
        return '매수 가능 금액';
      case 'explain_indicator':
        return '지표 설명';
      case 'recent_activity':
        return '최근 활동';
      case 'general_chat':
        return '안내';
      case 'explain':
        return '판단 설명';
      case 'portfolio':
        return '포트폴리오';
      case 'trade_prepare':
        return '주문 준비';
      case 'safety_block':
        return '안전';
      default:
        return strings.aiAssistant;
    }
  }
}

class _LocalQuoteCard extends StatelessWidget {
  const _LocalQuoteCard({
    required this.quote,
    required this.controller,
    required this.strings,
  });

  final _LocalQuote quote;
  final DashboardController controller;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final display = formatKrStockDisplay(
      quote.symbol,
      name: quote.name.isNotEmpty
          ? quote.name
          : KrStockCatalog.shared.displayName(quote.symbol),
    );
    final price = quote.data['current_price'] ?? quote.data['price'];
    final rows = <(String, Object)>[
      (strings.symbolLabel, quote.symbol),
      if (quote.error != null) ('\uC624\uB958', quote.error!),
      if (quote.data['change'] != null)
        ('\uC804\uC77C \uB300\uBE44', _formatKrw(quote.data['change']!)),
      if (quote.data['change_rate'] != null)
        ('\uBCC0\uB3D9\uB960', '${quote.data['change_rate']}%'),
      if (quote.data['timestamp'] != null)
        (strings.updated, quote.data['timestamp'].toString()),
      (strings.readOnly, strings.noOrderSubmit),
    ];
    return _DataCard(
      key: const ValueKey('ai-local-quote-card'),
      title: '$display ${strings.quickQuote}',
      primary: quote.error == null && price != null
          ? _formatKrw(price)
          : quote.error == null
              ? '\uAC00\uACA9 \uB370\uC774\uD130 \uC5C6\uC74C'
              : '\uC870\uD68C \uC2E4\uD328',
      rows: rows,
    );
  }
}

class _QuoteCard extends StatelessWidget {
  const _QuoteCard(
    this.response, {
    required this.strings,
    required this.controller,
  });

  final AgentChatV2Response response;
  final AppStrings strings;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final data = response.data['price'] is Map
        ? Map<String, dynamic>.from(response.data['price'] as Map)
        : const <String, dynamic>{};
    final value = data['price'] ?? data['current_price'];
    final currency = data['currency']?.toString() ?? 'KRW';
    final formatted = value == null
        ? strings.connectionError
        : currency == 'KRW'
            ? '${_group(value)}원'
            : '\$${value.toString()}';
    final stockDisplay = response.symbol == null
        ? (response.symbolName ?? '종목')
        : formatKrStockDisplay(
            response.symbol!,
            name: response.symbolName ??
                KrStockCatalog.shared.displayName(response.symbol!),
          );
    return _DataCard(
      key: const ValueKey('ai-v2-quote-card'),
      title: '$stockDisplay 현재가',
      primary: formatted,
      rows: [
        (strings.symbolLabel, response.symbol ?? '-'),
        (strings.currency, currency),
        if (data['timestamp'] != null)
          (strings.updated, data['timestamp'].toString()),
        (strings.readOnly, strings.noOrderSubmit),
      ],
    );
  }

  String _group(Object value) {
    final number = double.tryParse(value.toString().replaceAll(',', ''));
    if (number == null) return value.toString();
    return number.round().toString().replaceAllMapped(
          RegExp(r'(\d)(?=(\d{3})+(?!\d))'),
          (match) => '${match.group(1)},',
        );
  }
}

class _AnalysisCard extends StatelessWidget {
  const _AnalysisCard(
    this.response, {
    required this.strings,
    required this.controller,
  });

  final AgentChatV2Response response;
  final AppStrings strings;
  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    final flags = response.analysis['risk_flags'];
    final risk = flags is List && flags.isNotEmpty
        ? flags.take(3).join(', ')
        : strings.isKorean
            ? '추가 위험 없음'
            : 'No additional risk';
    return _DataCard(
      key: const ValueKey('ai-v2-analysis-card'),
      title: (response.symbol == null
              ? (response.symbolName ?? '종목')
              : formatKrStockDisplay(
                  response.symbol!,
                  name: response.symbolName ??
                      KrStockCatalog.shared.displayName(response.symbol!),
                )) +
          ' ${strings.analysis}',
      primary: strings.decisionLabel(response.action ?? 'hold'),
      rows: [
        (
          strings.finalScore,
          response.scores['final_score'] ?? response.scores['final_buy'] ?? '-'
        ),
        (strings.confidence, response.confidence ?? '-'),
        (strings.keyRisk, risk),
      ],
    );
  }
}

class _DecisionCard extends StatelessWidget {
  const _DecisionCard(this.response, {required this.strings});

  final AgentChatV2Response response;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final reasons = response.risk['block_reasons'];
    return _DataCard(
      key: const ValueKey('ai-v2-decision-card'),
      title: strings.recentDecisionExplanation,
      primary: strings.decisionLabel(response.action ?? 'hold'),
      rows: [
        (
          strings.primaryReason,
          reasons is List && reasons.isNotEmpty
              ? reasons.first
              : strings.recentDecisionLookup
        ),
      ],
    );
  }
}

class _PortfolioCard extends StatelessWidget {
  const _PortfolioCard(this.response, {required this.strings});

  final AgentChatV2Response response;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    final portfolio = response.portfolio;
    final positions = portfolio['positions'];
    return _DataCard(
      key: const ValueKey('ai-v2-portfolio-card'),
      title: strings.portfolio,
      primary: (portfolio['count']?.toString() ?? '0') +
          (strings.isKorean ? '개 종목' : ' positions'),
      rows: [
        if (portfolio['cash'] != null)
          (
            strings.cash,
            (portfolio['cash'].toString() + ' ' + (portfolio['currency'] ?? ''))
          ),
        if (positions is List && positions.isNotEmpty)
          (
            strings.firstHeldPosition,
            (positions.first as Map)['symbol']?.toString() ?? '-'
          ),
      ],
    );
  }
}

String _formatKrw(Object value) {
  final number = double.tryParse(value.toString().replaceAll(',', ''));
  if (number == null) return value.toString();
  final whole = number.round().toString().replaceAllMapped(
        RegExp(r'(\d)(?=(\d{3})+(?!\d))'),
        (match) => '${match.group(1)},',
      );
  return '\u20a9$whole';
}

class _DataCard extends StatelessWidget {
  const _DataCard({
    super.key,
    required this.title,
    required this.primary,
    required this.rows,
  });

  final String title;
  final String primary;
  final List<(String, Object)> rows;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final narrow = constraints.maxWidth < 480;
        return SectionCard(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (narrow) ...[
                Text(title,
                    style: const TextStyle(fontWeight: FontWeight.w800)),
                const SizedBox(height: 6),
                Text(
                  primary,
                  style: const TextStyle(
                      color: AppTheme.primaryAccent,
                      fontSize: 17,
                      fontWeight: FontWeight.w900),
                ),
              ] else
                Row(
                  children: [
                    Expanded(
                      child: Text(title,
                          style: const TextStyle(fontWeight: FontWeight.w800)),
                    ),
                    Flexible(
                      child: Text(primary,
                          textAlign: TextAlign.right,
                          style: const TextStyle(
                              color: AppTheme.primaryAccent,
                              fontSize: 17,
                              fontWeight: FontWeight.w900)),
                    ),
                  ],
                ),
              const SizedBox(height: 12),
              for (final row in rows)
                Padding(
                  padding: EdgeInsets.only(top: narrow ? 10 : 4),
                  child: narrow
                      ? Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(row.$1,
                                style: const TextStyle(color: Colors.white60)),
                            const SizedBox(height: 4),
                            Text(row.$2.toString(), softWrap: true),
                          ],
                        )
                      : Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Flexible(
                                flex: 2,
                                child: Text(row.$1,
                                    style: const TextStyle(
                                        color: Colors.white60))),
                            const SizedBox(width: 12),
                            Flexible(
                              flex: 3,
                              child: Text(row.$2.toString(),
                                  textAlign: TextAlign.right, softWrap: true),
                            ),
                          ],
                        ),
                ),
            ],
          ),
        );
      },
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.loading,
    required this.onSubmit,
    required this.strings,
  });

  final TextEditingController controller;
  final bool loading;
  final VoidCallback onSubmit;
  final AppStrings strings;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: Colors.black.withValues(alpha: 0.18),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: TextField(
                key: const ValueKey('ai-v2-input'),
                controller: controller,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) {
                  if (!loading) onSubmit();
                },
                decoration: InputDecoration(
                  hintText: strings.aiInputHint,
                  filled: true,
                ),
              ),
            ),
            const SizedBox(width: 8),
            FilledButton(
              key: const ValueKey('ai-v2-send'),
              onPressed: loading ? null : onSubmit,
              child: loading
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErrorCard extends StatelessWidget {
  const _ErrorCard(this.message);

  final String message;

  @override
  Widget build(BuildContext context) {
    return SectionCard(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.info_outline, color: Colors.orangeAccent),
          const SizedBox(width: 8),
          Expanded(
            child: Text(message, style: const TextStyle(height: 1.4)),
          ),
        ],
      ),
    );
  }
}

class _SafetyBadge extends StatelessWidget {
  const _SafetyBadge(this.label);

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      constraints: const BoxConstraints(minHeight: 36),
      alignment: Alignment.center,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: Colors.lightBlueAccent.withValues(alpha: 0.35),
        ),
      ),
      child: Text(label.toUpperCase(),
          style: const TextStyle(
              color: Colors.lightBlueAccent,
              fontSize: 11,
              fontWeight: FontWeight.w900)),
    );
  }
}
