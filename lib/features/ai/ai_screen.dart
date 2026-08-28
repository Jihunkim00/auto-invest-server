import 'package:flutter/material.dart';

import '../../core/i18n/app_language.dart';
import '../../core/i18n/app_strings.dart';
import '../../core/network/api_error_formatter.dart';
import '../../core/theme/app_theme.dart';
import '../../core/widgets/section_card.dart';
import '../../models/agent_chat_live_order_action.dart';
import '../../models/agent_chat_v2_response.dart';
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
    _input.clear();
    setState(() {
      _error = null;
      _loading = true;
      _entries.add(_AiEntry.user(text));
    });
    try {
      final kis = widget.controller.selectedProvider == SelectedProvider.kis;
      final response = await widget.controller.apiClient.sendAgentChatV2Message(
        message: text,
        conversationKey: _conversationKey,
        context: {
          'default_market': kis ? 'KR' : 'US',
          'default_provider': kis ? 'kis' : 'alpaca',
          'source': 'flutter_ai_v2',
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

class _AiEntry {
  const _AiEntry({this.userText, this.response, this.error});

  const _AiEntry.user(String value) : this(userText: value);
  const _AiEntry.assistant(AgentChatV2Response value) : this(response: value);
  const _AiEntry.error(String value) : this(error: value);

  final String? userText;
  final AgentChatV2Response? response;
  final String? error;
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
        spacing: 8,
        runSpacing: 8,
        children: [
          for (final item in actions.entries)
            ActionChip(
              key: ValueKey('ai-quick-' + item.key),
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
              labelPadding: const EdgeInsets.symmetric(horizontal: 4),
              materialTapTargetSize: MaterialTapTargetSize.padded,
              label: Text(labels[item.key] ?? item.key),
              onPressed: () => onSelected(item.value),
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
    required this.onConfirm,
    required this.onCancel,
  });

  final _AiEntry entry;
  final AppStrings strings;
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
        if (response.intent == 'quote') _QuoteCard(response, strings: strings),
        if (response.intent == 'analyze' ||
            response.intent == 'market_analysis')
          _AnalysisCard(response, strings: strings),
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

class _QuoteCard extends StatelessWidget {
  const _QuoteCard(this.response, {required this.strings});

  final AgentChatV2Response response;
  final AppStrings strings;

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
    return _DataCard(
      key: const ValueKey('ai-v2-quote-card'),
      title: '${response.symbolName ?? response.symbol ?? '종목'} 현재가',
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
  const _AnalysisCard(this.response, {required this.strings});

  final AgentChatV2Response response;
  final AppStrings strings;

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
      title: (response.symbolName ?? response.symbol ?? '종목') +
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
