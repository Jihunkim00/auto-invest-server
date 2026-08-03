from pathlib import Path
import json, sys
if '--check-source-only' in sys.argv:
    print(json.dumps({'source_symbol_count': 100}))
    raise SystemExit(0)
report_path = Path(sys.argv[sys.argv.index('--report-path') + 1])
summary_path = Path(sys.argv[sys.argv.index('--summary-path') + 1])
report_path.parent.mkdir(parents=True, exist_ok=True)
summary_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text('{', encoding='utf-8')
summary_path.write_text(json.dumps({
    'technical_pass_count': 1,
    'top_candidate': {'symbol': '005930', 'current_price': 52000},
    'selected_symbols': ['005930'],
    'report_path': str(report_path),
}), encoding='utf-8')
print(f'Report: {report_path}')
print(f'Summary: {summary_path}')
