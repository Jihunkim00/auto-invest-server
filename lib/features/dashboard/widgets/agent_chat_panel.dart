import 'package:flutter/material.dart';

import '../../../models/agent_chat_message.dart';
import '../dashboard_controller.dart';
import 'agent_chat_mini_panel.dart';

class AgentChatPanel extends StatelessWidget {
  const AgentChatPanel({
    super.key,
    required this.controller,
    this.onOpenManualOrder,
  });

  final DashboardController controller;
  final VoidCallback? onOpenManualOrder;

  @override
  Widget build(BuildContext context) {
    if (controller.agentChatMode == AgentChatPanelMode.fullscreen) {
      return const SizedBox.shrink();
    }
    return AgentChatMiniPanel(
      controller: controller,
      expanded: controller.agentChatMode == AgentChatPanelMode.expanded,
      onOpenManualOrder: onOpenManualOrder,
    );
  }
}
