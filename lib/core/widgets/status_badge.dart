import 'package:flutter/material.dart';

class StatusBadge extends StatelessWidget {
  const StatusBadge(
      {super.key,
      required this.text,
      required this.active,
      this.alert = false});

  final String text;
  final bool active;
  final bool alert;

  @override
  Widget build(BuildContext context) {
    final color =
        alert ? Colors.redAccent : (active ? Colors.greenAccent : Colors.grey);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Row(mainAxisSize: MainAxisSize.min, children: [
        Container(
            width: 8,
            height: 8,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle)),
        const SizedBox(width: 8),
        Text(text.toUpperCase(),
            style: TextStyle(
                color: color, fontSize: 11, fontWeight: FontWeight.w700)),
      ]),
    );
  }
}
