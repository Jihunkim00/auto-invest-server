import 'package:flutter/material.dart';
import '../../../core/utils/timestamp_formatter.dart';

/// Current account health, separate from the historical slot execution reason.
class KisOrderReconciliationStatus extends StatelessWidget {
  const KisOrderReconciliationStatus({super.key, required this.status});

  final Map<String, dynamic> status;

  @override
  Widget build(BuildContext context) {
    final unresolved = (status['unresolved_count'] as num?)?.toInt() ?? 0;
    final message = status['buy_hold_message'];
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '주문 동기화 · 확인 ${status['checked_count'] ?? 0} · '
          '종료 ${status['finalized_count'] ?? 0} · 미확정 $unresolved · '
          '수동 검토 ${status['manual_review_count'] ?? 0}',
          key: const ValueKey('kis-order-reconciliation-counts'),
          style: const TextStyle(color: Colors.white60, fontSize: 12),
        ),
        if (status['last_synced_at'] != null)
          Text('마지막 확인 ${formatTimestampWithKst(status['last_synced_at'] as String?)}',
              style: const TextStyle(color: Colors.white60, fontSize: 12)),
        if (unresolved > 0 && message is String)
          Text(message, key: const ValueKey('kis-order-reconciliation-hold')),
        if (unresolved > 0 && status['last_failure_reason'] != null)
          Text('주문 조회 확인 필요: ${_failureMessage(status['last_failure_reason'])}',
              key: const ValueKey('kis-order-reconciliation-failure')),
      ],
    );
  }

  static String _failureMessage(Object? reason) {
    switch (reason) {
      case 'kis_odno_missing':
      case 'local_order_number_conflict':
        return '브로커 주문번호를 확인해 주세요.';
      case 'broker_order_record_missing':
      case 'broker_order_not_uniquely_verified':
        return '주문 이력을 확인하지 못해 재확인이 필요합니다.';
      case 'history_date_out_of_supported_range':
        return '자동 조회 가능 기간을 벗어나 수동 확인이 필요합니다.';
      case 'history_incomplete':
      case 'invalid_continuation_response':
      case 'call_budget_exceeded':
      case 'read_deadline_exceeded':
        return '주문 조회가 완료되지 않아 재확인 중입니다.';
      case 'broker_order_identity_mismatch':
      case 'order_environment_mismatch':
      case 'order_account_mismatch':
      case 'account_scope_mismatch':
        return '주문과 계좌 정보가 일치하는지 확인해 주세요.';
      default:
        return '계좌 연결과 주문 상태를 다시 확인해 주세요.';
    }
  }
}
