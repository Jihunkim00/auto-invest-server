import 'package:flutter/material.dart';

class OperationToggleCard extends StatelessWidget {
  const OperationToggleCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
    this.pending = false,
    this.enabled = true,
    this.lastResult,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
  final bool pending;
  final bool enabled;
  final String? lastResult;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Column(
        children: [
          SwitchListTile(
            title: Text(title),
            subtitle: Text(subtitle),
            value: value,
            onChanged: (!enabled || pending) ? null : onChanged,
            secondary: pending
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : Icon(
                    value ? Icons.check_circle : Icons.radio_button_unchecked,
                    color: value ? Colors.greenAccent : Colors.white54,
                  ),
          ),
          if (lastResult != null)
            Padding(
              padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text(lastResult!, style: const TextStyle(fontSize: 12, color: Colors.white70)),
              ),
            ),
          if (!enabled)
            const Padding(
              padding: EdgeInsets.fromLTRB(16, 0, 16, 12),
              child: Align(
                alignment: Alignment.centerLeft,
                child: Text('This control is not implemented on backend yet.', style: TextStyle(fontSize: 12, color: Colors.orangeAccent)),
              ),
            ),
        ],
      ),
    );
  }
}
