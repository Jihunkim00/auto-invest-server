import 'package:flutter/material.dart';

class LanguageToggleChip extends StatelessWidget {
  const LanguageToggleChip({super.key, required this.isKorean, required this.onTap});
  final bool isKorean;
  final VoidCallback onTap;
  @override
  Widget build(BuildContext context) {
    return InkWell(
      key: const ValueKey('language-toggle-chip'),
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        height: 28,
        padding: const EdgeInsets.symmetric(horizontal: 10),
        decoration: BoxDecoration(color: const Color(0xFFEAF1FF), borderRadius: BorderRadius.circular(14)),
        child: Row(mainAxisSize: MainAxisSize.min, children: [
          const Icon(Icons.translate, size: 14, color: Color(0xFF2563EB)),
          const SizedBox(width: 4),
          Text(isKorean ? 'KR' : 'ENG', style: const TextStyle(color: Color(0xFF2563EB), fontWeight: FontWeight.w700)),
        ]),
      ),
    );
  }
}
