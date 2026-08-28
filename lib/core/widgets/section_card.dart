import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

class SectionCard extends StatelessWidget {
  const SectionCard(
      {super.key,
      required this.child,
      this.padding = const EdgeInsets.all(16)});

  final Widget child;
  final EdgeInsets padding;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: AppTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppTheme.cardRadius),
        side: const BorderSide(color: AppTheme.hairline),
      ),
      clipBehavior: Clip.antiAlias,
      child: Padding(
        padding: padding,
        child: child,
      ),
    );
  }
}
