import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_invest_dashboard/features/dashboard/dashboard_controller.dart';
import 'package:auto_invest_dashboard/features/dashboard/widgets/strategy_profile_card.dart';
import 'package:auto_invest_dashboard/models/strategy_profile.dart';

void main() {
  testWidgets('strategy profile card renders active profile and limits',
      (tester) async {
    String? appliedProfile;
    final profiles = [
      _profile('safe', '안정형'),
      _profile('balanced', '보통형'),
      _profile('aggressive', '고수익형', active: true),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: StrategyProfileCard(
              profiles: profiles,
              activeProfile: profiles.last,
              loading: false,
              error: null,
              applyingProfileName: null,
              onRefresh: () async => const ActionResult(
                success: true,
                message: 'refreshed',
              ),
              onApply: (profileName) async {
                appliedProfile = profileName;
                return const ActionResult(
                  success: true,
                  message: 'applied',
                );
              },
            ),
          ),
        ),
      ),
    );

    expect(find.text('Strategy Risk Profile'), findsOneWidget);
    expect(find.textContaining('고수익형'), findsWidgets);
    expect(find.text('PROFILE ONLY'), findsOneWidget);
    expect(find.text('NO ORDER SUBMIT'), findsOneWidget);
    expect(find.text('STRATEGY TARGET'), findsOneWidget);
    expect(find.text('Monthly target'), findsOneWidget);
    expect(find.text('5.0%-8.0%'), findsWidgets);
    expect(find.text('Monthly loss cap'), findsOneWidget);
    expect(find.textContaining('손실 변동성'), findsOneWidget);
    expect(find.byKey(const ValueKey('strategy-profile-apply-safe')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('strategy-profile-apply-balanced')),
        findsOneWidget);
    expect(find.byKey(const ValueKey('strategy-profile-apply-aggressive')),
        findsOneWidget);
    expect(find.text('Submit order'), findsNothing);
    expect(find.textContaining('dry_run'), findsNothing);
    expect(find.textContaining('kill_switch'), findsNothing);

    await tester.tap(find.byKey(const ValueKey('strategy-profile-apply-safe')));
    await tester.pumpAndSettle();

    expect(
      find.byKey(const ValueKey('strategy-profile-confirm-dialog')),
      findsOneWidget,
    );
    expect(find.textContaining('No order is submitted'), findsOneWidget);

    await tester.tap(find.byKey(const ValueKey('strategy-profile-confirm-apply')));
    await tester.pumpAndSettle();

    expect(appliedProfile, 'safe');
  });
}

StrategyProfile _profile(
  String profileName,
  String displayName, {
  bool active = false,
}) {
  final aggressive = profileName == 'aggressive';
  final balanced = profileName == 'balanced';
  return StrategyProfile.fromJson({
    'id': aggressive
        ? 3
        : balanced
            ? 2
            : 1,
    'profile_name': profileName,
    'display_name': displayName,
    'description': '$displayName profile',
    'monthly_target_return_pct': aggressive
        ? 0.06
        : balanced
            ? 0.04
            : 0.015,
    'monthly_target_min_pct': aggressive
        ? 0.05
        : balanced
            ? 0.03
            : 0.01,
    'monthly_target_max_pct': aggressive
        ? 0.08
        : balanced
            ? 0.05
            : 0.02,
    'monthly_max_loss_pct': aggressive ? -0.06 : -0.04,
    'daily_max_loss_pct': aggressive ? -0.015 : -0.01,
    'max_order_notional_pct': aggressive ? 0.06 : 0.04,
    'max_order_notional_krw': aggressive ? 80000 : 50000,
    'max_trades_per_day': aggressive ? 2 : 1,
    'max_positions': aggressive ? 5 : 3,
    'buy_score_threshold': aggressive ? 62 : 68,
    'sell_score_threshold': aggressive ? 55 : 60,
    'stop_loss_pct': aggressive ? -0.03 : -0.02,
    'take_profit_pct': aggressive ? 0.06 : 0.04,
    'max_holding_days': aggressive ? 10 : 7,
    'stop_after_monthly_target': !aggressive,
    'reduce_size_after_loss': true,
    'consecutive_loss_reduce_threshold': aggressive ? 3 : 2,
    'is_active': active,
    'is_builtin': true,
  });
}
