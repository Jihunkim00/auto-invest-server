import 'package:flutter/material.dart';

import '../../../models/agent_command.dart';
import '../../../models/agent_plan.dart';

class AgentPlanReviewCard extends StatelessWidget {
  const AgentPlanReviewCard({
    super.key,
    required this.plan,
    this.parseResult,
    this.onRunSafeAction,
    this.onPrepareManualTicket,
    this.runLoading = false,
    this.prepareLoading = false,
    this.compact = false,
  });

  final AgentPlan plan;
  final AgentCommandParseResult? parseResult;
  final VoidCallback? onRunSafeAction;
  final VoidCallback? onPrepareManualTicket;
  final bool runLoading;
  final bool prepareLoading;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final badges = _badgesFor(plan, parseResult);
    return Container(
      key: const Key('agent-plan-review-card'),
      width: double.infinity,
      padding: EdgeInsets.all(compact ? 10 : 14),
      decoration: BoxDecoration(
        color: Colors.white.withValues(alpha: 0.06),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.white.withValues(alpha: 0.12)),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
          const Icon(Icons.fact_check_outlined, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child:
                Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Text(
                'Prepared from your message',
                style: TextStyle(
                  fontSize: compact ? 13 : 15,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 3),
              Text(
                plan.userVisibleSummary.isEmpty
                    ? plan.planSummary
                    : plan.userVisibleSummary,
                maxLines: compact ? 2 : null,
                overflow: compact ? TextOverflow.ellipsis : null,
                style: const TextStyle(color: Colors.white70, height: 1.25),
              ),
            ]),
          ),
        ]),
        const SizedBox(height: 10),
        Wrap(spacing: 8, runSpacing: 8, children: [
          _InfoPill(label: 'Type', value: plan.commandType),
          _InfoPill(label: 'Risk', value: plan.riskLevel),
          if (plan.symbol != null) _InfoPill(label: 'Symbol', value: plan.symbol!),
          if (plan.side != 'none') _InfoPill(label: 'Side', value: plan.side),
          if (plan.quantity != null)
            _InfoPill(label: 'Qty', value: plan.quantity.toString()),
          if (plan.notional != null)
            _InfoPill(
              label: 'Amount',
              value: '${plan.currency ?? ''} ${plan.notional}'.trim(),
            ),
          _InfoPill(label: 'Status', value: plan.status),
        ]),
        if (!compact) ...[
          const SizedBox(height: 10),
          Wrap(spacing: 7, runSpacing: 7, children: [
            for (final badge in badges) _SafetyBadge(text: badge),
          ]),
          const SizedBox(height: 10),
          Text(
            'No broker submit was called. Manual validation and confirm_live stay in Trading.',
            style: TextStyle(
              color: Colors.lightBlueAccent.withValues(alpha: 0.95),
              fontSize: 12,
              height: 1.25,
            ),
          ),
        ],
        const SizedBox(height: 12),
        _ActionArea(
          plan: plan,
          runLoading: runLoading,
          prepareLoading: prepareLoading,
          onRunSafeAction: onRunSafeAction,
          onPrepareManualTicket: onPrepareManualTicket,
        ),
      ]),
    );
  }
}

class _ActionArea extends StatelessWidget {
  const _ActionArea({
    required this.plan,
    required this.runLoading,
    required this.prepareLoading,
    required this.onRunSafeAction,
    required this.onPrepareManualTicket,
  });

  final AgentPlan plan;
  final bool runLoading;
  final bool prepareLoading;
  final VoidCallback? onRunSafeAction;
  final VoidCallback? onPrepareManualTicket;

  @override
  Widget build(BuildContext context) {
    if (plan.isAuthRequired) {
      return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        OutlinedButton.icon(
          key: const ValueKey('agent-auth-required-button'),
          onPressed: null,
          icon: const Icon(Icons.lock_outline, size: 16),
          label: const Text('Auth Required'),
        ),
        const SizedBox(height: 6),
        const Text(
          'Approval flow is not connected to live execution yet.',
          style: TextStyle(color: Colors.orangeAccent, fontSize: 12),
        ),
      ]);
    }
    if (plan.isBlocked) {
      return const Text(
        'Blocked by backend policy. No action is available.',
        style: TextStyle(color: Colors.orangeAccent, fontSize: 12),
      );
    }
    if (plan.canPrepareManualTicket) {
      return FilledButton.icon(
        key: const ValueKey('agent-prepare-manual-ticket'),
        onPressed: prepareLoading ? null : onPrepareManualTicket,
        icon: prepareLoading
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.edit_note_outlined, size: 16),
        label: Text(prepareLoading ? 'Preparing...' : 'Prepare Manual Ticket'),
      );
    }
    if (plan.canRunSafeAction) {
      return FilledButton.icon(
        key: const ValueKey('agent-run-safe-action'),
        onPressed: runLoading ? null : onRunSafeAction,
        icon: runLoading
            ? const SizedBox(
                width: 16,
                height: 16,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.play_circle_outline, size: 16),
        label: Text(runLoading ? 'Running...' : 'Run Safe Action'),
      );
    }
    return const Text(
      'Review only. No chat action is available for this plan.',
      style: TextStyle(color: Colors.white70, fontSize: 12),
    );
  }
}

class _InfoPill extends StatelessWidget {
  const _InfoPill({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.20),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withValues(alpha: 0.10)),
      ),
      child: Text(
        '$label: $value',
        style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _SafetyBadge extends StatelessWidget {
  const _SafetyBadge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final color = text.contains('AUTH') || text.contains('BLOCKED')
        ? Colors.orangeAccent
        : text.contains('NO AUTO') || text.contains('SAFE')
            ? Colors.greenAccent
            : Colors.lightBlueAccent;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.36)),
      ),
      child: Text(
        text,
        style: TextStyle(
          color: color,
          fontSize: 10,
          fontWeight: FontWeight.w900,
        ),
      ),
    );
  }
}

List<String> _badgesFor(AgentPlan plan, AgentCommandParseResult? parseResult) {
  final badges = <String>[
    parseResult?.fallbackUsed == true ? 'FALLBACK PARSER' : 'GPT-BACKED',
    'SERVER-SIDE API',
    'NO AUTO SUBMIT',
  ];
  if (plan.canPrepareManualTicket) {
    badges.addAll([
      'PREFILL ONLY',
      'MANUAL VALIDATION REQUIRED',
      'CONFIRM_LIVE MANUAL',
    ]);
  }
  if (plan.canRunSafeAction) badges.add('SAFE EXECUTION ONLY');
  if (plan.isAuthRequired) badges.add('AUTH REQUIRED');
  if (plan.isBlocked) badges.add('BLOCKED');
  if (plan.riskLevel == 'read_only') badges.add('READ ONLY');
  if (plan.riskLevel == 'analysis_only') badges.add('ANALYSIS ONLY');
  return badges;
}
