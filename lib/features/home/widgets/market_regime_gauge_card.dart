import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/section_card.dart';
import '../../../models/market_regime.dart';

class MarketRegimeGaugeCard extends StatelessWidget {
  const MarketRegimeGaugeCard({
    super.key,
    required this.regime,
    this.loading = false,
    this.error,
  });

  final MarketRegime? regime;
  final bool loading;
  final String? error;

  @override
  Widget build(BuildContext context) {
    final stage = regime?.stage;
    final color = _stageColor(stage);
    final stageText = loading
        ? '\uACC4\uC0B0 \uC911'
        : error != null
            ? '\uD604\uC7AC \uC9C0\uD45C\uB97C \uBD88\uB7EC\uC62C \uC218 \uC5C6\uC74C'
            : regime == null
                ? '\uC790\uB8CC \uB300\uAE30'
                : regime!.status == 'pending'
                    ? '\uD655\uC815 \uB300\uAE30'
                    : regime!.status == 'insufficient_data'
                        ? '\uD655\uC815 \uBCF4\uB958'
                        : stage == null
                            ? '\uD655\uC778 \uD544\uC694'
                            : '${stage}\uB2E8\uACC4 \u00B7 ${regime!.shortLabel ?? regime!.stageLabel ?? _stageName(stage)}';

    return SectionCard(
      key: const ValueKey('home-market-regime-gauge-card'),
      padding: EdgeInsets.zero,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          key: const ValueKey('home-market-regime-gauge-tap'),
          borderRadius: BorderRadius.circular(AppTheme.cardRadius),
          onTap: () => showModalBottomSheet<void>(
            context: context,
            backgroundColor: AppTheme.surface,
            isScrollControlled: true,
            builder: (_) => MarketRegimeDetailSheet(regime: regime),
          ),
          child: Padding(
            padding: const EdgeInsets.all(12),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        '\uC7A5\uAE30 \uC2DC\uC7A5 \uAD6D\uBA74',
                        style: Theme.of(context).textTheme.titleSmall,
                      ),
                    ),
                    const SizedBox(width: 6),
                    Flexible(
                      child: Text(
                        stageText,
                        key: const ValueKey('home-market-regime-stage-text'),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.end,
                        style: TextStyle(
                          color: color,
                          fontSize: 12,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                    ),
                    const SizedBox(width: 4),
                    const Icon(Icons.info_outline,
                        size: 16, color: Colors.white54),
                  ],
                ),
                Align(
                  alignment: Alignment.center,
                  child: SizedBox(
                    width: 180,
                    height: 48,
                    child: CustomPaint(
                      key: ValueKey('market-regime-gauge-stage-${stage}'),
                      painter: _MarketRegimeGaugePainter(stage: stage),
                    ),
                  ),
                ),
                Text(
                  '\uC810\uC218 ${_format(regime?.marketScore)}   3\uC8FC ${_formatChange(regime?.scoreChange3w)}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white70, fontSize: 11),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _MarketRegimeGaugePainter extends CustomPainter {
  const _MarketRegimeGaugePainter({required this.stage});

  final int? stage;

  static const _colors = <Color>[
    AppTheme.danger,
    AppTheme.warning,
    AppTheme.primaryAccent,
    AppTheme.positive,
    AppTheme.warning,
    AppTheme.danger,
  ];

  @override
  void paint(Canvas canvas, Size size) {
    final center = Offset(size.width / 2, size.height - 10);
    final radius = math.min(size.width * 0.43, size.height - 22);
    final rect = Rect.fromCircle(center: center, radius: radius);
    const segment = math.pi / 6;
    const gap = 0.045;
    final track = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..strokeCap = StrokeCap.butt;

    for (var index = 0; index < 6; index++) {
      track.color = stage == index + 1
          ? _colors[index]
          : Colors.white.withValues(alpha: 0.16);
      canvas.drawArc(
        rect,
        math.pi + index * segment + gap / 2,
        segment - gap,
        false,
        track,
      );
    }

    if (stage == null || stage! < 1 || stage! > 6) return;
    final angle = math.pi + (stage! - 0.5) * segment;
    final length = radius * 0.7;
    final tip = Offset(center.dx + math.cos(angle) * length,
        center.dy + math.sin(angle) * length);
    final needle = Paint()
      ..color = Colors.white
      ..strokeWidth = 2.5
      ..strokeCap = StrokeCap.round;
    canvas.drawLine(center, tip, needle);
    canvas.drawCircle(center, 5, Paint()..color = _colors[stage! - 1]);
    canvas.drawCircle(center, 2, Paint()..color = AppTheme.surface);
  }

  @override
  bool shouldRepaint(covariant _MarketRegimeGaugePainter oldDelegate) =>
      oldDelegate.stage != stage;
}

class MarketRegimeDetailSheet extends StatelessWidget {
  const MarketRegimeDetailSheet({super.key, required this.regime});
  final MarketRegime? regime;

  @override
  Widget build(BuildContext context) {
    final value = regime;
    final conditions = value?.bullishTransition.conditions ?? const [];
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
        child: SingleChildScrollView(
          child: Column(
            key: const ValueKey('home-market-regime-detail-sheet'),
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                      child: Text('장기 시장 국면',
                          style: Theme.of(context).textTheme.titleLarge)),
                  IconButton(
                    key: const ValueKey('market-regime-detail-close'),
                    tooltip: '닫기',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.close),
                  ),
                ],
              ),
              const SizedBox(height: 10),
              const Text('현재', style: TextStyle(color: Colors.white54)),
              const SizedBox(height: 3),
              Text(
                value?.hasStage == true
                    ? '${value!.stage}단계 · ${value.stageLabel ?? value.shortLabel ?? _stageName(value.stage!)}'
                    : _statusLabel(value),
                style: TextStyle(
                    color: _stageColor(value?.stage),
                    fontSize: 18,
                    fontWeight: FontWeight.w800),
              ),
              const SizedBox(height: 4),
              Text(value?.summary ?? '저장된 시장 국면 데이터가 없습니다.'),
              const SizedBox(height: 18),
              _ScoreRow(
                  label: '시장 점수',
                  value: _format(value?.marketScore),
                  emphasize: true),
              _ScoreRow(label: 'KOSPI', value: _format(value?.kospiScore)),
              _ScoreRow(label: 'NASDAQ', value: _format(value?.nasdaqScore)),
              _ScoreRow(
                  label: '3주 변화', value: _formatChange(value?.scoreChange3w)),
              const SizedBox(height: 16),
              Text('계산 방식', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 7),
              const Text('시장 점수 = KOSPI 60% + NASDAQ 40%',
                  style: TextStyle(color: Colors.white70)),
              const SizedBox(height: 4),
              const Text('각 시장 점수 = 추세 40% + 모멘텀 40% + RSI 20%',
                  style: TextStyle(color: Colors.white70)),
              const SizedBox(height: 4),
              const Text('추세: EMA20 / EMA40 / ATR14',
                  style: TextStyle(color: Colors.white54)),
              const Text('모멘텀: MACD Histogram',
                  style: TextStyle(color: Colors.white54)),
              const Text('보조 지표: RSI14 / KOSPI 52주 낙폭',
                  style: TextStyle(color: Colors.white54)),
              if (value?.kospi.drawdown52w != null) ...[
                const SizedBox(height: 8),
                _ScoreRow(
                    label: 'KOSPI 52주 낙폭',
                    value: '${value!.kospi.drawdown52w!.toStringAsFixed(2)}%'),
              ],
              const SizedBox(height: 18),
              Text('상승 전환 확인 조건',
                  style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 8),
              if (conditions.isEmpty)
                const Text('확인할 조건 데이터가 없습니다.',
                    style: TextStyle(color: Colors.white54))
              else
                ...conditions.map((condition) => _ConditionRow(condition)),
              const SizedBox(height: 16),
              Text(_sourceDescription(value),
                  style: const TextStyle(color: Colors.white54, fontSize: 12)),
              if (value?.nextScheduledCalculation != null) ...[
                const SizedBox(height: 5),
                Text('다음 계산: ${value!.nextScheduledCalculation!.toLocal()}',
                    style:
                        const TextStyle(color: Colors.white54, fontSize: 12)),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _ScoreRow extends StatelessWidget {
  const _ScoreRow(
      {required this.label, required this.value, this.emphasize = false});
  final String label;
  final String value;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          Expanded(
              child:
                  Text(label, style: const TextStyle(color: Colors.white70))),
          Text(value,
              style: TextStyle(
                  fontSize: emphasize ? 20 : 15, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}

class _ConditionRow extends StatelessWidget {
  const _ConditionRow(this.condition);
  final MarketRegimeCondition condition;

  @override
  Widget build(BuildContext context) {
    final color = condition.passed ? AppTheme.positive : Colors.white38;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
              condition.passed
                  ? Icons.check_circle_outline
                  : Icons.circle_outlined,
              size: 17,
              color: color),
          const SizedBox(width: 8),
          Expanded(
              child: Text(condition.label,
                  style: TextStyle(color: color, height: 1.3))),
        ],
      ),
    );
  }
}

String _format(double? value) => value?.toStringAsFixed(2) ?? '—';

String _formatChange(double? value) {
  if (value == null) return '—';
  final sign = value > 0 ? '+' : '';
  return '$sign${value.toStringAsFixed(1)}';
}

String _stageName(int stage) => switch (stage) {
      1 => '하락',
      2 => '바닥 탐색',
      3 => '상승 전환',
      4 => '상승',
      5 => '상승 둔화',
      6 => '하락 전환',
      _ => '확정 대기',
    };

Color _stageColor(int? stage) => switch (stage) {
      1 => AppTheme.danger,
      2 => AppTheme.warning,
      3 => AppTheme.primaryAccent,
      4 => AppTheme.positive,
      5 => AppTheme.warning,
      6 => AppTheme.danger,
      _ => Colors.white54,
    };

String _statusLabel(MarketRegime? regime) {
  if (regime?.status == 'pending') return '확정 대기';
  if (regime?.status == 'insufficient_data') return '안정 보류';
  return '시장 국면 데이터 없음';
}

String _sourceDescription(MarketRegime? regime) {
  final source = regime?.dataSource;
  final nasdaq = source?.nasdaq;
  if (source?.nasdaqIsProxy == true || nasdaq?.isProxy == true) {
    return 'NASDAQ 데이터: ${nasdaq?.label ?? 'NASDAQ-100 proxy (QQQ)'}';
  }
  return '데이터 출처: ${source?.kospi?.provider ?? '—'} · ${nasdaq?.label ?? 'NASDAQ Composite'}';
}
