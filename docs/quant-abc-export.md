# ABC observation export

`python -m app.scripts.export_quant_abc_logs` exports the persisted observations
and labels to CSV (default). It opens an existing SQLite database with `mode=ro`
and `PRAGMA query_only=ON`; it never runs startup, migrations, replay, GPT, KIS,
or broker code. `--database` selects a file without changing `DATABASE_URL`.
Otherwise the application's `.env` / environment settings supply `DATABASE_URL`.
The exporter currently supports file-backed SQLite only.

```powershell
python -m app.scripts.export_quant_abc_logs `
  --database auto_invest.db `
  --month 2026-10 `
  --format both `
  --output data/abc_exports

python -m app.scripts.export_quant_abc_logs `
  --from-date 2026-10-01 --to-date 2026-10-31 `
  --official-only --passed-only --format json
```

The first command writes `abc_observations_2026-10.csv` and
`abc_observations_2026-10.json`. `--output` accepts a directory or an explicit
CSV/JSON filename; `both` uses that filename's stem for both extensions.

| Option | Behavior |
| --- | --- |
| `--database PATH` | Existing SQLite file; defaults to configured database |
| `--month YYYY-MM` | Korea calendar month |
| `--date YYYY-MM-DD` | One Korea calendar date |
| `--from-date` / `--to-date` | Inclusive bounds; either bound may be omitted |
| `--trigger-source VALUE` | Exact stored trigger source |
| `--official-only` | Require full analysis quality |
| `--include-partial` | Include all qualities, which is also the default |
| `--format csv\|json\|both` | CSV by default |
| `--output PATH` | `data/abc_exports` by default |
| `--a-rank-max` | Funnel annotation threshold, default 5 |
| `--c-min-score` | Funnel annotation threshold, default 65 |
| `--gpt-min-score` | Funnel annotation threshold, default 60 |
| `--final-min-score` | Funnel annotation threshold, default 65 |
| `--passed-only` | Export only rows passing the analysis funnel |

Choose one date selector: month, single date, or date range. Naive timestamps
are interpreted as Korea time; aware timestamps are converted to Korea time
for filtering. Raw timestamp values are preserved as ISO-8601 strings.

Every observation produces one row using a LEFT JOIN on the unique outcome
`observation_id`. An observation without a label remains in the export with
null outcome values. All stored columns are included. The five adjacent funnel
columns are `a_rank`, `a_quant_buy_score`, `c_reversal_score`,
`a_gpt_buy_score`, and `a_final_score`.

Outcome names that collide with observation names receive an `outcome_` prefix
(`outcome_id`, `outcome_symbol`, `outcome_observed_at`, `outcome_created_at`).
Outcome `outcome_status` is called `outcome_label_status`, preserving the
observation's `outcome_status`. Horizon returns, entry price, MFE/MAE, and all
other outcome columns keep their stored names. Column order is fixed regardless
of SQLite column creation/migration order. Indicator and metadata JSON
columns retain their raw strings. If an old database has no outcome table,
only observation columns and derived fields are exported.

JSON is a UTF-8 array of objects with numbers, booleans, and nulls preserved.
CSV has the same fields, uses empty cells for nulls and `true`/`false` booleans.
The printed counts describe the exported rows after the requested filters.

`gpt_score_available` means the GPT score is not null; a real score of zero is
available. `entry_funnel_pass` means A rank <= 5, C >= 65, GPT >= 60, and Final
>= 65 (unless export thresholds are supplied). These are analysis annotations
and provide no execution authority. Threshold options alone never discard rows.

`official_quality` reconstructs the existing preview full/partial criteria:
the shared intraday metadata must have `validation_status=ok`; each present
B/C analysis must have quality >= 1 and a finite score. B requires at least
two bars in 15m/30m/60m; C requires at least two in 15m/30m, as recorded in the
indicator snapshots. Missing evidence, stale snapshots, or reduced quality
remain non-official. This flag describes observation inputs, so an outcome
may still be pending. `Partial/non-official` counts all remaining records,
including missing/invalid quality evidence.

Startup adds nullable `a_gpt_buy_score FLOAT` only if absent. It does not
backfill historical observations. Logging stores validated `ai_buy_score`
only when GPT was used and its status is completed; legacy items without an
explicit status use `gpt_used=True`. Explicit failed, incomplete, or not-run
statuses always store null, even if a stale score is present. Final Buy Score
continues to use the existing `a_final_score` column.

For a database predating the new column, the exporter prints a migration
notice and projects `a_gpt_buy_score=NULL` without modifying the database.
September GPT-disabled replay scores remain null; Final is never used to infer
GPT scores. New scores can be persisted after normal application DB startup
has applied the migration. Exporting does not apply it.
