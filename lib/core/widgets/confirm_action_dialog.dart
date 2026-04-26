import 'package:flutter/material.dart';

Future<bool> showConfirmActionDialog(
  BuildContext context, {
  required String title,
  required String description,
}) async {
  return await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text(title),
          content: Text(description),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancel')),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Confirm')),
          ],
        ),
      ) ??
      false;
}
