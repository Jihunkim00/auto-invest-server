import 'package:flutter/material.dart';

class LogFilterChips extends StatelessWidget {
  const LogFilterChips({super.key, required this.value, required this.onChanged});

  final String value;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    const filters = ['All', 'Manual', 'Scheduler', 'Hold', 'Skipped', 'Buy', 'Sell'];
    return Wrap(
      spacing: 8,
      children: [
        for (final f in filters)
          ChoiceChip(
            label: Text(f),
            selected: value == f,
            onSelected: (_) => onChanged(f),
          ),
      ],
    );
  }
}
