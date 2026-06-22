import 'package:flutter/material.dart';

import '../../../models/agent_chat_live_order_action.dart';
import '../../../models/agent_chat_message.dart';
import '../dashboard_controller.dart';
import 'agent_chat_live_order_confirmation_card.dart';
import 'agent_chat_live_order_readiness_card.dart';
import 'agent_chat_live_order_status_card.dart';
import 'agent_plan_review_card.dart';
import 'agent_chat_tool_result_card.dart';

class AgentChatFullPanel extends StatefulWidget {
  const AgentChatFullPanel({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  State<AgentChatFullPanel> createState() => _AgentChatFullPanelState();
}

class _AgentChatFullPanelState extends State<AgentChatFullPanel> {
  final TextEditingController _input = TextEditingController();
  final ScrollController _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.controller.initializeAgentConversation();
    });
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    return Material(
      color: Colors.black.withValues(alpha: 0.88),
      child: SafeArea(
        child: Container(
          key: const Key('agent-chat-full-panel'),
          margin: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: const Color(0xFF161616),
            borderRadius: BorderRadius.circular(14),
            border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
          ),
          child: Column(children: [
            _FullToolbar(controller: controller),
            const Divider(height: 1, color: Colors.white12),
            Expanded(
              child: ListView(
                key: const ValueKey('agent-chat-message-thread'),
                controller: _scroll,
                padding: const EdgeInsets.all(16),
                children: [
                  const _SafetyNotice(),
                  if (_showReadinessCard(controller))
                    AgentChatLiveOrderReadinessCard(
                      readiness: controller.agentChatLiveOrderReadiness,
                      loading: controller.isLoadingAgentChatLiveOrderReadiness,
                      error: controller.agentChatLiveOrderSettingsError,
                      applyingPreset: controller.applyingAgentChatLiveOrderPreset,
                      onRefresh: controller.refreshAgentChatLiveOrderReadiness,
                      onApplyPreset: controller.applyAgentChatLiveOrderPreset,
                    ),
                  if (controller.isLoadingAgentHistory) ...[
                    const SizedBox(height: 10),
                    const Text(
                      'Loading previous chat...',
                      style: TextStyle(
                        color: Colors.lightBlueAccent,
                        fontSize: 12,
                      ),
                    ),
                  ],
                  if (controller.agentHistoryError != null) ...[
                    const SizedBox(height: 10),
                    Text(
                      controller.agentHistoryError!,
                      style: const TextStyle(
                        color: Colors.orangeAccent,
                        fontSize: 12,
                      ),
                    ),
                  ],
                  const SizedBox(height: 12),
                  for (final message in controller.agentMessages)
                    _MessageBubble(
                      message: message,
                      onSuggestionSelected: _sendSuggestion,
                      onConfirmLiveOrder: _confirmLiveOrder,
                      onCancelLiveOrder: _cancelLiveOrder,
                      onRefreshLiveOrder: _syncLiveOrder,
                      liveOrderBusy: controller.isAgentLiveOrderActionBusy,
                    ),
                  if (controller.isAgentParsing ||
                      controller.isAgentPlanCreating) ...[
                    const SizedBox(height: 8),
                    const _TypingIndicator(),
                  ],
                  if (controller.latestAgentPlan != null) ...[
                    const SizedBox(height: 12),
                    AgentPlanReviewCard(
                      plan: controller.latestAgentPlan!,
                      parseResult: controller.latestAgentCommand,
                      runLoading: controller.isAgentRunning,
                      prepareLoading: controller.isAgentPreparingTicket,
                      onRunSafeAction: () => _runSafeAction(context),
                      onPrepareManualTicket: () => _prepareTicket(context),
                    ),
                  ],
                ],
              ),
            ),
            const Divider(height: 1, color: Colors.white12),
            Padding(
              padding: const EdgeInsets.all(12),
              child: _FullInputRow(
                controller: _input,
                busy: controller.isAgentParsing ||
                    controller.isAgentPlanCreating ||
                    controller.isAgentRunning ||
                    controller.isAgentPreparingTicket,
                onSubmitted: _send,
              ),
            ),
          ]),
        ),
      ),
    );
  }

  Future<void> _send() async {
    final text = _input.text;
    _input.clear();
    final result = await widget.controller.sendAgentMessage(text);
    if (!mounted) return;
    if (!result.success) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(result.message)),
      );
    }
    await Future<void>.delayed(const Duration(milliseconds: 40));
    if (_scroll.hasClients) {
      await _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _sendSuggestion(String text) async {
    _input.text = text;
    await _send();
  }

  Future<void> _runSafeAction(BuildContext context) async {
    final result = await widget.controller.runAgentSafePlan();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _prepareTicket(BuildContext context) async {
    final result = await widget.controller.prepareAgentManualTicket();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
    if (result.success) widget.onOpenManualOrder?.call();
  }

  Future<void> _confirmLiveOrder(AgentChatLiveOrderAction action) async {
    final result = await widget.controller.confirmAgentChatLiveOrder(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
    await Future<void>.delayed(const Duration(milliseconds: 40));
    if (_scroll.hasClients) {
      await _scroll.animateTo(
        _scroll.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _cancelLiveOrder(AgentChatLiveOrderAction action) async {
    final result = await widget.controller.cancelAgentChatLiveOrder(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _syncLiveOrder(AgentChatLiveOrderAction action) async {
    final result = await widget.controller.syncAgentChatLiveOrder(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _FullToolbar extends StatelessWidget {
  const _FullToolbar({required this.controller});

  final DashboardController controller;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      child: Row(children: [
        const Icon(Icons.auto_awesome_outlined, size: 20),
        const SizedBox(width: 8),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Agent Assistant',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
              ),
              const SizedBox(height: 2),
              Text(
                controller.activeAgentConversationKey == null
                    ? 'Natural language command review'
                    : 'Conversation ${controller.activeAgentConversationKey}',
                style: TextStyle(color: Colors.white70, fontSize: 12),
              ),
            ],
          ),
        ),
        const Flexible(
          child: Wrap(
            alignment: WrapAlignment.end,
            spacing: 6,
            runSpacing: 6,
            children: [
              _ToolbarBadge(text: 'GPT-BACKED'),
              _ToolbarBadge(text: 'SAFE MODE'),
              _ToolbarBadge(text: 'SERVER-SIDE API'),
            ],
          ),
        ),
        const SizedBox(width: 8),
        IconButton(
          key: const ValueKey('agent-chat-full-new-chat'),
          tooltip: 'New Chat',
          onPressed: () {
            controller.startNewAgentConversation();
          },
          icon: const Icon(Icons.add_comment_outlined, size: 18),
        ),
        IconButton(
          key: const ValueKey('agent-chat-full-refresh-history'),
          tooltip: 'Refresh History',
          onPressed: () {
            final key = controller.activeAgentConversationKey;
            if (key == null) {
              controller.restoreLatestAgentConversation();
            } else {
              controller.loadAgentConversationHistory(key);
            }
          },
          icon: const Icon(Icons.history, size: 18),
        ),
        IconButton(
          key: const ValueKey('agent-chat-full-archive'),
          tooltip: 'Archive',
          onPressed: () {
            controller.archiveAgentConversation();
          },
          icon: const Icon(Icons.archive_outlined, size: 18),
        ),
        IconButton(
          key: const ValueKey('agent-chat-minimize'),
          tooltip: 'Minimize',
          onPressed: () => controller.setAgentChatMode(AgentChatPanelMode.mini),
          icon: const Icon(Icons.minimize, size: 20),
        ),
        IconButton(
          key: const ValueKey('agent-chat-full-resize'),
          tooltip: 'Resize',
          onPressed: controller.cycleAgentChatMode,
          icon: const Icon(Icons.close_fullscreen, size: 18),
        ),
        IconButton(
          key: const ValueKey('agent-chat-close'),
          tooltip: 'Close',
          onPressed: () =>
              controller.setAgentChatMode(AgentChatPanelMode.collapsed),
          icon: const Icon(Icons.close, size: 20),
        ),
      ]),
    );
  }
}

class _SafetyNotice extends StatelessWidget {
  const _SafetyNotice();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: Colors.lightBlueAccent.withValues(alpha: 0.24),
        ),
      ),
      child: const Text(
        'Live KIS orders from Agent Chat require an explicit confirmation card. Backend validation and risk gates rerun before submit. OpenAI API is called only from the FastAPI server.',
        style: TextStyle(color: Colors.lightBlueAccent, height: 1.25),
      ),
    );
  }
}

class _MessageBubble extends StatelessWidget {
  const _MessageBubble({
    required this.message,
    required this.onSuggestionSelected,
    required this.onConfirmLiveOrder,
    required this.onCancelLiveOrder,
    required this.onRefreshLiveOrder,
    required this.liveOrderBusy,
  });

  final AgentChatMessage message;
  final ValueChanged<String> onSuggestionSelected;
  final Future<void> Function(AgentChatLiveOrderAction action)
      onConfirmLiveOrder;
  final Future<void> Function(AgentChatLiveOrderAction action)
      onCancelLiveOrder;
  final Future<void> Function(AgentChatLiveOrderAction action)
      onRefreshLiveOrder;
  final bool Function(int actionId) liveOrderBusy;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == AgentChatRole.user;
    final isError = message.role == AgentChatRole.error;
    final alignment = isUser ? Alignment.centerRight : Alignment.centerLeft;
    final color = isError
        ? Colors.redAccent.withValues(alpha: 0.18)
        : isUser
            ? Colors.white.withValues(alpha: 0.14)
            : Colors.white.withValues(alpha: 0.07);
    return Align(
      alignment: alignment,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 680),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(10),
          border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
        ),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
          Text(
            isUser ? 'You' : 'Agent',
            style: const TextStyle(
              color: Colors.white54,
              fontSize: 11,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 5),
          Text(
            message.text,
            softWrap: true,
            style: const TextStyle(height: 1.3),
          ),
          if (message.safetyBadges.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(spacing: 6, runSpacing: 6, children: [
              for (final badge in message.safetyBadges)
                _ToolbarBadge(text: badge),
            ]),
          ],
          if (!isUser &&
              (message.resultCards.isNotEmpty ||
                  message.followUpSuggestions.isNotEmpty)) ...[
            const SizedBox(height: 10),
            AgentChatToolResultCardList(
              cards: message.resultCards,
              followUpSuggestions: message.followUpSuggestions,
              onSuggestionSelected: onSuggestionSelected,
            ),
          ],
          if (!isUser && message.liveOrderAction != null)
            if (message.liveOrderAction!.isPending)
              AgentChatLiveOrderConfirmationCard(
                action: message.liveOrderAction!,
                busy: liveOrderBusy(message.liveOrderAction!.actionId),
                onConfirm: onConfirmLiveOrder,
                onCancel: onCancelLiveOrder,
              )
            else
              AgentChatLiveOrderStatusCard(
                action: message.liveOrderAction!,
                busy: liveOrderBusy(message.liveOrderAction!.actionId),
                onRefresh: onRefreshLiveOrder,
                onCancel: onCancelLiveOrder,
              ),
        ]),
      ),
    );
  }
}

class _TypingIndicator extends StatelessWidget {
  const _TypingIndicator();

  @override
  Widget build(BuildContext context) {
    return const Align(
      alignment: Alignment.centerLeft,
      child: Text(
        'Agent is typing...',
        style: TextStyle(color: Colors.lightBlueAccent, fontSize: 12),
      ),
    );
  }
}

bool _showReadinessCard(DashboardController controller) {
  return controller.agentChatLiveOrderReadiness != null ||
      controller.isLoadingAgentChatLiveOrderReadiness ||
      controller.agentChatLiveOrderSettingsError != null;
}

class _FullInputRow extends StatelessWidget {
  const _FullInputRow({
    required this.controller,
    required this.busy,
    required this.onSubmitted,
  });

  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSubmitted;

  @override
  Widget build(BuildContext context) {
    return Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
      Expanded(
        child: TextField(
          key: const ValueKey('agent-chat-full-input'),
          controller: controller,
          textInputAction: TextInputAction.send,
          minLines: 1,
          maxLines: 4,
          onSubmitted: (_) {
            if (!busy) onSubmitted();
          },
          decoration: InputDecoration(
            hintText: 'Message Agent Assistant...',
            filled: true,
            fillColor: Colors.black.withValues(alpha: 0.28),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(10),
              borderSide:
                  BorderSide(color: Colors.white.withValues(alpha: 0.1)),
            ),
          ),
        ),
      ),
      const SizedBox(width: 8),
      FilledButton.icon(
        key: const ValueKey('agent-chat-full-send'),
        onPressed: busy ? null : onSubmitted,
        icon: busy
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.send, size: 16),
        label: const Text('Send'),
      ),
    ]);
  }
}

class _ToolbarBadge extends StatelessWidget {
  const _ToolbarBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: Colors.lightBlueAccent.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(
          color: Colors.lightBlueAccent.withValues(alpha: 0.35),
        ),
      ),
      child: Text(
        text,
        style: const TextStyle(
          color: Colors.lightBlueAccent,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}
