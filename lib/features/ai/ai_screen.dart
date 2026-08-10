import 'package:flutter/material.dart';

import '../../core/i18n/app_language.dart';
import '../../core/network/api_error_formatter.dart';
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
    return Material(
      color: Colors.transparent,
      child: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: EdgeInsets.fromLTRB(16, 14, 16, 4),
              child: Row(
                children: [
                  Icon(Icons.auto_awesome, color: Colors.lightBlueAccent),
                  SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('AI Assistant',
                            style: TextStyle(
                                fontSize: 24, fontWeight: FontWeight.w900)),
                        Text('분석과 설명, 주문 준비를 도와드립니다.',
                            style: TextStyle(color: Colors.white70)),
                      ],
                    ),
                  ),
                  _SafetyBadge('NO AUTO SUBMIT'),
                  IconButton(
                    key: const ValueKey('ai-open-admin'),
                    tooltip: 'Advanced / Admin',
                    onPressed: widget.onOpenAdmin,
                    icon: const Icon(Icons.admin_panel_settings_outlined),
                  ),
                ],
              ),
            ),
            _QuickActions(onSelected: _quickAction),
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
                  if (_entries.isEmpty) const _WelcomeCard(),
                  for (final entry in _entries)
                    _EntryView(
                      entry: entry,
                      onConfirm: _confirm,
                      onCancel: _cancel,
                    ),
                  if (_loading)
                    const Align(
                      alignment: Alignment.centerLeft,
                      child: Padding(
                        padding: EdgeInsets.all(8),
                        child: Text('분석 중…',
                            style: TextStyle(color: Colors.lightBlueAccent)),
                      ),
                    ),
                ],
              ),
            ),
            _InputBar(
              controller: _input,
              loading: _loading,
              onSubmit: _send,
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
      return '현재 안전 중지 상태라 주문할 수 없습니다.';
    }
    if (value.contains('dry_run') || value.contains('dry run')) {
      return '현재 모의/안전 모드입니다.';
    }
    if (value.contains('open order')) {
      return '이미 처리 중인 주문이 있습니다.';
    }
    return 'Agent 응답을 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.';
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
  const _QuickActions({required this.onSelected});

  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    const actions = <String, String>{
      '종목 분석': '삼성전자 분석해줘',
      '포트폴리오': '내 포트폴리오 보여줘',
      '최근 판단': '최근 자동매매 판단 알려줘',
      '왜 안 샀어?': '오늘 왜 매수 안 했어?',
    };
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
      child: Row(
        children: [
          for (final item in actions.entries)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ActionChip(
                key: ValueKey('ai-quick-' + item.key),
                label: Text(item.key),
                onPressed: () => onSelected(item.value),
              ),
            ),
        ],
      ),
    );
  }
}

class _WelcomeCard extends StatelessWidget {
  const _WelcomeCard();

  @override
  Widget build(BuildContext context) {
    return const SectionCard(
      key: ValueKey('ai-v2-welcome-card'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('무엇을 도와드릴까요?',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800)),
          SizedBox(height: 8),
          Text(
            '종목 분석, 최근 HOLD 이유, 포트폴리오, 주문 준비를 요청할 수 있습니다. '
            '실제 주문은 별도 확인과 기존 backend safety gate를 거칩니다.',
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
    required this.onConfirm,
    required this.onCancel,
  });

  final _AiEntry entry;
  final Future<void> Function(AgentChatLiveOrderAction) onConfirm;
  final Future<void> Function(AgentChatLiveOrderAction) onCancel;

  @override
  Widget build(BuildContext context) {
    if (entry.userText != null) {
      return Align(
        alignment: Alignment.centerRight,
        child: Container(
          key: const ValueKey('ai-v2-user-message'),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.12),
            borderRadius: BorderRadius.circular(12),
          ),
          child: Text(entry.userText!),
        ),
      );
    }
    if (entry.error != null) return _ErrorCard(entry.error!);
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
              Row(
                children: [
                  const Icon(Icons.auto_awesome,
                      size: 16, color: Colors.lightBlueAccent),
                  const SizedBox(width: 6),
                  Text(_label(response.intent),
                      style: const TextStyle(
                          color: Colors.lightBlueAccent,
                          fontWeight: FontWeight.w800)),
                  const Spacer(),
                  _SafetyBadge(response.status.replaceAll('_', ' ')),
                ],
              ),
              const SizedBox(height: 8),
              Text(response.message,
                  key: const ValueKey('ai-v2-response-message'),
                  style: const TextStyle(height: 1.35)),
            ],
          ),
        ),
        if (response.intent == 'analyze') _AnalysisCard(response),
        if (response.intent == 'explain') _DecisionCard(response),
        if (response.intent == 'portfolio') _PortfolioCard(response),
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

  String _label(String intent) {
    switch (intent) {
      case 'analyze':
        return 'Analysis';
      case 'explain':
        return 'Decision explanation';
      case 'portfolio':
        return 'Portfolio';
      case 'trade_prepare':
        return 'Order preview';
      case 'safety_block':
        return 'Safety';
      default:
        return 'Agent';
    }
  }
}

class _AnalysisCard extends StatelessWidget {
  const _AnalysisCard(this.response);

  final AgentChatV2Response response;

  @override
  Widget build(BuildContext context) {
    final flags = response.analysis['risk_flags'];
    final risk = flags is List && flags.isNotEmpty
        ? flags.take(3).join(', ')
        : '추가 위험 없음';
    return _DataCard(
      key: const ValueKey('ai-v2-analysis-card'),
      title: (response.symbolName ?? response.symbol ?? '종목') + ' 분석',
      primary: response.action ?? 'HOLD',
      rows: [
        (
          'Final score',
          response.scores['final_score'] ?? response.scores['final_buy'] ?? '-'
        ),
        ('Confidence', response.confidence ?? '-'),
        ('Risk', risk),
      ],
    );
  }
}

class _DecisionCard extends StatelessWidget {
  const _DecisionCard(this.response);

  final AgentChatV2Response response;

  @override
  Widget build(BuildContext context) {
    final reasons = response.risk['block_reasons'];
    return _DataCard(
      key: const ValueKey('ai-v2-decision-card'),
      title: '최근 판단 설명',
      primary: response.action ?? 'HOLD',
      rows: [
        (
          '주요 이유',
          reasons is List && reasons.isNotEmpty
              ? reasons.first
              : '최근 decision/log 기반 조회'
        ),
      ],
    );
  }
}

class _PortfolioCard extends StatelessWidget {
  const _PortfolioCard(this.response);

  final AgentChatV2Response response;

  @override
  Widget build(BuildContext context) {
    final portfolio = response.portfolio;
    final positions = portfolio['positions'];
    return _DataCard(
      key: const ValueKey('ai-v2-portfolio-card'),
      title: '내 포트폴리오',
      primary: (portfolio['count']?.toString() ?? '0') + '개 종목',
      rows: [
        if (portfolio['cash'] != null)
          (
            '현금',
            (portfolio['cash'].toString() + ' ' + (portfolio['currency'] ?? ''))
          ),
        if (positions is List && positions.isNotEmpty)
          ('첫 보유 종목', (positions.first as Map)['symbol']?.toString() ?? '-'),
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
    return SectionCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(title,
                    style: const TextStyle(fontWeight: FontWeight.w800)),
              ),
              Text(primary,
                  style: const TextStyle(
                      color: Colors.lightBlueAccent,
                      fontSize: 17,
                      fontWeight: FontWeight.w900)),
            ],
          ),
          const SizedBox(height: 8),
          for (final row in rows)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  Expanded(
                      child: Text(row.$1,
                          style: const TextStyle(color: Colors.white60))),
                  Flexible(
                      child: Text(row.$2.toString(),
                          textAlign: TextAlign.right,
                          overflow: TextOverflow.ellipsis)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}

class _InputBar extends StatelessWidget {
  const _InputBar({
    required this.controller,
    required this.loading,
    required this.onSubmit,
  });

  final TextEditingController controller;
  final bool loading;
  final VoidCallback onSubmit;

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
                decoration: const InputDecoration(
                  hintText: '무엇을 도와드릴까요?',
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
        children: [
          const Icon(Icons.info_outline, color: Colors.orangeAccent),
          const SizedBox(width: 8),
          Expanded(child: Text(message)),
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
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
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
              fontSize: 10,
              fontWeight: FontWeight.w900)),
    );
  }
}
