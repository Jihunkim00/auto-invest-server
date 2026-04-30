import 'package:flutter/material.dart';

class OperationToggleCard extends StatelessWidget {
  const OperationToggleCard({
    super.key,
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
    this.loading = false,
  });

  final String title;
  final String subtitle;
  final bool value;
  final bool loading;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: SwitchListTile(
        title: Text(title),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(subtitle),
            if (loading) ...[
              const SizedBox(height: 4),
              const Text('Updating...', style: TextStyle(color: Colors.amberAccent, fontSize: 12)),
            ],
          ],
        ),
        value: value,
        onChanged: loading ? null : onChanged,
        secondary: loading ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2.0)) : null,
      ),
    );
  }
}
