import 'package:flutter/material.dart';

import '../../../core/widgets/section_card.dart';
import '../../../models/agent_chat_live_order_action.dart';
import '../../../models/agent_chat_message.dart';
import '../../../models/agent_chat_strategy_action.dart';
import '../dashboard_controller.dart';
import 'agent_chat_live_order_confirmation_card.dart';
import 'agent_chat_live_order_readiness_card.dart';
import 'agent_chat_live_order_status_card.dart';
import 'agent_chat_strategy_action_card.dart';
import 'agent_plan_review_card.dart';
import 'agent_chat_tool_result_card.dart';

class AgentChatMiniPanel extends StatefulWidget {
  const AgentChatMiniPanel({
    super.key,
    required this.controller,
    this.expanded = false,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final bool expanded;
  final VoidCallback? onOpenManualOrder;

  @override
  State<AgentChatMiniPanel> createState() => _AgentChatMiniPanelState();
}

class _AgentChatMiniPanelState extends State<AgentChatMiniPanel> {
  final TextEditingController _input = TextEditingController();

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
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final controller = widget.controller;
    final collapsed = controller.agentChatMode == AgentChatPanelMode.collapsed;
    return SectionCard(
      padding: const EdgeInsets.all(14),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.auto_awesome_outlined, size: 20),
          const SizedBox(width: 8),
          const Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                'Agent Assistant',
                style: TextStyle(fontSize: 17, fontWeight: FontWeight.w900),
              ),
              SizedBox(height: 3),
              Text(
                'Ask for analysis, portfolio, or confirmed KIS order prep.',
                style: TextStyle(color: Colors.white70, height: 1.25),
              ),
            ]),
          ),
          IconButton(
            key: const ValueKey('agent-chat-new-chat'),
            tooltip: 'New Chat',
            onPressed: () => _startNewChat(context),
            icon: const Icon(Icons.add_comment_outlined, size: 18),
          ),
          IconButton(
            key: const ValueKey('agent-chat-refresh-history'),
            tooltip: 'Refresh History',
            onPressed: () => _refreshHistory(context),
            icon: const Icon(Icons.history, size: 18),
          ),
          IconButton(
            key: const ValueKey('agent-chat-collapse'),
            tooltip: collapsed ? 'Expand Agent Chat' : 'Collapse Agent Chat',
            onPressed: () => controller.setAgentChatMode(
              collapsed
                  ? AgentChatPanelMode.mini
                  : AgentChatPanelMode.collapsed,
            ),
            icon: Icon(collapsed
                ? Icons.keyboard_arrow_up
                : Icons.keyboard_arrow_down),
          ),
          IconButton(
            key: const ValueKey('agent-chat-resize'),
            tooltip: 'Resize Agent Chat',
            onPressed: controller.cycleAgentChatMode,
            icon: const Icon(Icons.open_in_full, size: 18),
          ),
          IconButton(
            key: const ValueKey('agent-chat-fullscreen'),
            tooltip: 'Open Full Agent Chat',
            onPressed: () =>
                controller.setAgentChatMode(AgentChatPanelMode.fullscreen),
            icon: const Icon(Icons.fullscreen, size: 20),
          ),
        ]),
        const SizedBox(height: 10),
        const Wrap(spacing: 8, runSpacing: 8, children: [
          _AgentBadge(text: 'GPT-BACKED'),
          _AgentBadge(text: 'SERVER-SIDE API'),
          _AgentBadge(text: 'SAFE MODE'),
          _AgentBadge(text: 'CONFIRM REQUIRED'),
        ]),
        if (controller.isLoadingAgentHistory) ...[
          const SizedBox(height: 10),
          const Text(
            'Loading previous chat...',
            style: TextStyle(color: Colors.lightBlueAccent, fontSize: 12),
          ),
        ],
        if (controller.agentHistoryError != null) ...[
          const SizedBox(height: 10),
          Text(
            controller.agentHistoryError!,
            style: const TextStyle(color: Colors.orangeAccent, fontSize: 12),
          ),
        ],
        if (!collapsed) ...[
          if (_showReadinessCard(controller)) ...[
            const SizedBox(height: 12),
            AgentChatLiveOrderReadinessCard(
              readiness: controller.agentChatLiveOrderReadiness,
              loading: controller.isLoadingAgentChatLiveOrderReadiness,
              error: controller.agentChatLiveOrderSettingsError,
              applyingPreset: controller.applyingAgentChatLiveOrderPreset,
              onRefresh: controller.refreshAgentChatLiveOrderReadiness,
              onApplyPreset: controller.applyAgentChatLiveOrderPreset,
              compact: !widget.expanded,
            ),
            const SizedBox(height: 12),
          ] else
            const SizedBox(height: 12),
          _RecentAgentMessages(
            messages: controller.agentMessages,
            maxItems: widget.expanded ? 5 : 3,
            onSuggestionSelected: _sendSuggestion,
            onConfirmLiveOrder: _confirmLiveOrder,
            onCancelLiveOrder: _cancelLiveOrder,
            onRefreshLiveOrder: _syncLiveOrder,
            liveOrderBusy: controller.isAgentLiveOrderActionBusy,
            onConfirmStrategyAction: _confirmStrategyAction,
            onCancelStrategyAction: _cancelStrategyAction,
            strategyActionBusy: controller.isAgentStrategyActionBusy,
          ),
          if (controller.latestAgentPlan != null) ...[
            const SizedBox(height: 10),
            AgentPlanReviewCard(
              plan: controller.latestAgentPlan!,
              parseResult: controller.latestAgentCommand,
              compact: !widget.expanded,
              runLoading: controller.isAgentRunning,
              prepareLoading: controller.isAgentPreparingTicket,
              onRunSafeAction: () => _runSafeAction(context),
              onPrepareManualTicket: () => _prepareTicket(context),
            ),
          ],
          const SizedBox(height: 12),
          _AgentInputRow(
            controller: _input,
            busy: controller.isAgentParsing || controller.isAgentPlanCreating,
            onSubmitted: _send,
          ),
        ],
      ]),
    );
  }

  Future<void> _send() async {
    final text = _input.text;
    _input.clear();
    final result = await widget.controller.sendAgentMessage(text);
    if (!mounted || result.success) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _sendSuggestion(String text) async {
    _input.text = text;
    await _send();
  }

  Future<void> _startNewChat(BuildContext context) async {
    final result = await widget.controller.startNewAgentConversation();
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _refreshHistory(BuildContext context) async {
    final key = widget.controller.activeAgentConversationKey;
    final result = key == null
        ? await widget.controller.restoreLatestAgentConversation()
        : await widget.controller.loadAgentConversationHistory(key);
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
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

  Future<void> _confirmStrategyAction(
    AgentChatStrategyAction action,
  ) async {
    final result = await widget.controller.confirmAgentChatStrategyAction(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  Future<void> _cancelStrategyAction(AgentChatStrategyAction action) async {
    final result = await widget.controller.cancelAgentChatStrategyAction(action);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }
}

class _RecentAgentMessages extends StatelessWidget {
  const _RecentAgentMessages({
    required this.messages,
    required this.maxItems,
    required this.onSuggestionSelected,
    required this.onConfirmLiveOrder,
    required this.onCancelLiveOrder,
    required this.onRefreshLiveOrder,
    required this.liveOrderBusy,
    required this.onConfirmStrategyAction,
    required this.onCancelStrategyAction,
    required this.strategyActionBusy,
  });

  final List<AgentChatMessage> messages;
  final int maxItems;
  final ValueChanged<String> onSuggestionSelected;
  final Future<void> Function(AgentChatLiveOrderAction action)
      onConfirmLiveOrder;
  final Future<void> Function(AgentChatLiveOrderAction action)
      onCancelLiveOrder;
  final Future<void> Function(AgentChatLiveOrderAction action)
      onRefreshLiveOrder;
  final bool Function(int actionId) liveOrderBusy;
  final Future<void> Function(AgentChatStrategyAction action)
      onConfirmStrategyAction;
  final Future<void> Function(AgentChatStrategyAction action)
      onCancelStrategyAction;
  final bool Function(int actionId) strategyActionBusy;

  @override
  Widget build(BuildContext context) {
    final visible = messages.reversed.take(maxItems).toList().reversed;
    return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
      for (final message in visible)
        _MiniMessageLine(
          message: message,
          onSuggestionSelected: onSuggestionSelected,
          onConfirmLiveOrder: onConfirmLiveOrder,
          onCancelLiveOrder: onCancelLiveOrder,
          onRefreshLiveOrder: onRefreshLiveOrder,
          liveOrderBusy: liveOrderBusy,
          onConfirmStrategyAction: onConfirmStrategyAction,
          onCancelStrategyAction: onCancelStrategyAction,
          strategyActionBusy: strategyActionBusy,
        ),
      if (messages.any((message) => message.status == AgentChatStatus.parsing))
        const Padding(
          padding: EdgeInsets.only(top: 4),
          child: Text(
            'Agent is typing...',
            style: TextStyle(color: Colors.lightBlueAccent, fontSize: 12),
          ),
        ),
    ]);
  }
}

class _MiniMessageLine extends StatelessWidget {
  const _MiniMessageLine({
    required this.message,
    required this.onSuggestionSelected,
    required this.onConfirmLiveOrder,
    required this.onCancelLiveOrder,
    required this.onRefreshLiveOrder,
    required this.liveOrderBusy,
    required this.onConfirmStrategyAction,
    required this.onCancelStrategyAction,
    required this.strategyActionBusy,
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
  final Future<void> Function(AgentChatStrategyAction action)
      onConfirmStrategyAction;
  final Future<void> Function(AgentChatStrategyAction action)
      onCancelStrategyAction;
  final bool Function(int actionId) strategyActionBusy;

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == AgentChatRole.user;
    final color = message.role == AgentChatRole.error
        ? Colors.redAccent
        : isUser
            ? Colors.white
            : Colors.white70;
    return Padding(
      padding: const EdgeInsets.only(bottom: 6),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SizedBox(
          width: 58,
          child: Text(
            isUser ? 'You' : 'Agent',
            style: const TextStyle(color: Colors.white54, fontSize: 12),
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                message.text,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(color: color, fontSize: 13, height: 1.25),
              ),
              if (!isUser && message.safetyBadges.isNotEmpty) ...[
                const SizedBox(height: 4),
                Wrap(
                  spacing: 4,
                  runSpacing: 4,
                  children: [
                    for (final badge in message.safetyBadges.take(4))
                      _AgentBadge(text: badge),
                  ],
                ),
              ],
              if (!isUser &&
                  (message.resultCards.isNotEmpty ||
                      message.followUpSuggestions.isNotEmpty)) ...[
                const SizedBox(height: 8),
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
                    compact: true,
                  )
                else
                  AgentChatLiveOrderStatusCard(
                    action: message.liveOrderAction!,
                    busy: liveOrderBusy(message.liveOrderAction!.actionId),
                    onRefresh: onRefreshLiveOrder,
                    onCancel: onCancelLiveOrder,
                    compact: true,
                  ),
              if (!isUser && message.strategyAction != null)
                AgentChatStrategyActionCard(
                  action: message.strategyAction!,
                  busy: strategyActionBusy(message.strategyAction!.actionId),
                  onConfirm: onConfirmStrategyAction,
                  onCancel: onCancelStrategyAction,
                  compact: true,
                ),
            ],
          ),
        ),
      ]),
    );
  }
}

class _AgentInputRow extends StatelessWidget {
  const _AgentInputRow({
    required this.controller,
    required this.busy,
    required this.onSubmitted,
  });

  final TextEditingController controller;
  final bool busy;
  final VoidCallback onSubmitted;

  @override
  Widget build(BuildContext context) {
    return Row(children: [
      Expanded(
        child: TextField(
          key: const ValueKey('agent-chat-mini-input'),
          controller: controller,
          textInputAction: TextInputAction.send,
          minLines: 1,
          maxLines: 2,
          onSubmitted: (_) {
            if (!busy) onSubmitted();
          },
          decoration: InputDecoration(
            hintText: 'Ask Agent Assistant...',
            isDense: true,
            filled: true,
            fillColor: Colors.black.withValues(alpha: 0.20),
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
        key: const ValueKey('agent-chat-mini-send'),
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

bool _showReadinessCard(DashboardController controller) {
  return controller.agentChatLiveOrderReadiness != null ||
      controller.isLoadingAgentChatLiveOrderReadiness ||
      controller.agentChatLiveOrderSettingsError != null;
}

class _AgentBadge extends StatelessWidget {
  const _AgentBadge({required this.text});

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
