# Real statements, pilot run (18 Nov 2026)

`scripts/eval_real.sh` with ft4, code 3437b0a. 30 genuine statements from friends and family
(Axis 5, J&K 5, SBI 6, HDFC 4, Kotak 3, PNB 2, ICICI 2, IDBI 1, FamApp 1, Slice 1); 28 read,
2 not opened (password missing or wrong); all 28 have a text layer (none image-only). The
statements were deleted by the run. Thresholds as fitted on the synthetic test set; every
statement is genuine, so every flag is a false alarm.

| Signal | Flagged @1% threshold | Assessed | False-alarm rate (95% CI) | Flagged @5% |
| --- | ---: | ---: | --- | ---: |
| Image (ft4) | 4 | 28 | 14.3% (5.7–31.5%) | 4 |
| Financial (PDF text) | 7 | 19 | 36.8% (19.1–59.0%) | 7 |
| PDF structure | 9 | 28 | 32.1% (17.9–50.7%) | 9 |
| OCR arithmetic | 8 | 22 | 36.4% (19.7–57.0%) | 15 |
| **Fused** | **7** | 28 | **25.0% (12.7–43.4%)** | 7 |

Fused flags by bank (1%): Kotak 3/3, IDBI 1/1, PNB 1/1, Slice 1/1, SBI 1/5; Axis 0/5, HDFC 0/4,
J&K 0/5, ICICI 0/2, FamApp 0/1. Checks that fired: font_anomaly 11, running_balance 6,
non_embedded_font 5, row_format 5, duplicate_font 5, modified_after_creation 2,
closing_balance 2, incremental_update 1.

## Reading

The thresholds fitted on synthetic statements do not transfer to real ones: ForgeLens flags a
quarter of genuine real statements, against 1% of genuine synthetic ones. The false alarms come
from the rule-based signals, not the image model, and cluster by bank (every Kotak statement),
which points at how particular banks build their PDFs, not at chance:

- **PDF structure** (font_anomaly 11, non_embedded_font 5, duplicate_font 5): real bank software
  uses secondary fonts, standard non-embedded fonts and per-page font subsets that our
  generator (one tool, two embedded fonts) never produces, so the checks read them as edits.
- **Financial** (running_balance 6, row_format 5 of 19 parsed): the reader misreads some real
  table layouts (row order, debit/credit columns, wrapped rows).
- **OCR arithmetic**: the same layouts, read from the image.

Next: a second run with privacy-safe diagnostics (`--diagnostics`: producer software, font
names, which checks fired on how many spans or rows, balance breaks under other readings of the
table; no text, dates or amounts), then rules that tolerate what genuine bank software does,
checked statement by statement against these 28 without fitting to them.

## Diagnostics run (19 Nov 2026) and rule fixes

Second run with `--diagnostics` (same 28 statements read; S001 and S012 not opened): the same
7 flags. The diagnostics (no text, dates or amounts; kept off the repository) show where each
false alarm comes from:

| Cause | Statements | Fix (code 20 Nov) |
| --- | --- | --- |
| Weights of one family read as a second family (SourceSans3-SemiBold, Mulish-Black, Rubik-Medium) or as a duplicate (Rubik-Regular / Rubik-Medium) | Kotak ×3, ICICI ×2, Slice | `family_weight()`: family, weight class and italic, separately |
| FPDF style suffixes ("montserrat", "montserratB", "montserratsb") | FamApp | suffixes stripped; style-suffixed spellings are one family |
| Symbol font (ZapfDingbats) | PNB | symbol fonts ignored |
| Non-embedded standard font that is the document's body font (Helvetica, Times) | IDBI, PNB | a font drawing ≥20% of the text is not patched-in text |
| Second font for headings and labels that repeat on every page | Axis, Kotak | "template text": a font whose text mostly repeats on other pages |
| Apple print-to-PDF: a new font subset for each page | SBI (Safari) | one subset per page on disjoint pages is not a duplicate |
| 0.00 printed in the empty debit/credit column | IDBI (461 row_format) | a zero beside a non-zero amount is an empty cell |
| Rows whose amount the reader did not find (printed web pages) | J&K ×3 | counted as unread, left out of the balance chain |

On 64 fresh synthetic PDF edits and 16 genuine statements the fixed rules flag exactly what
the old ones did (PDF structure 64/64 forged, 0/16 genuine; financial 31/64, 0/16). Still
unexplained and left alone: a second font on the last page(s) only (IDBI, PNB, SBI Safari),
balance breaks on two Axis statements, and the OCR misreads on long statements. A third run
measures the effect.

## Third run, with the fixed rules (20 Nov 2026)

Code 499a6fa, image model ft4; 29 of 30 statements read (S001 now opened; S012 password
still wrong).

| Signal | Run 1–2 (28 read) | Run 3 (29 read) | Run 3 flagged |
| --- | ---: | ---: | --- |
| Image (ft4) | 4 (14%) | 4 (14%) | S004, S005, S024, S027 |
| Financial | 7 of 19 (37%) | 7 of 19 (37%) | S004, S006, S008, S010, S011, S014, S029 |
| PDF structure | 9 (32%) | **5 (17%)** | S001, S002, S008, S017, S026 |
| OCR arithmetic | 8 of 22 (36%) | 8 of 22 (36%) | unchanged |
| **ForgeLens (fused)** | 7 (25%, CI 13–43%) | **3 (10.3%, CI 3.6–26.4%)** | S001, S017, S026 |

Fused flags by bank: Kotak 3/3 → 0/3, IDBI 1/1 → 0/1, Slice 1/1 → 0/1; still flagged: both
PNB statements (2/2) and the SBI statement printed from Safari (1/5). Checks that fired:
running_balance 6, font_anomaly 5 (was 11), non_embedded_font 5, duplicate_font 4 (was 5),
row_format 1 (was 5), modified_after_creation 2, closing_balance 2, incremental_update 1.

The image model's and the financial and OCR signals' own flags are unchanged (the image model
is not fused on text PDFs; the financial and OCR flags do not reach the fused threshold).

## Synthetic test set with the fixed rules (20 Nov 2026, tag final-ft6)

Signals recomputed on the test set and phone copies with the fixed rules; image model ft6.
Fused, threshold per kind of copy: **60%** of all 1,996 forgeries at 1% false alarms (64% at
5%), the same as with the old rules (60%); one threshold 57% (was 58%). PDF structure alone
catches 98% of digital PDF edits (was 100%); fused still 100%. So the fixes cost the synthetic
results nothing that fusion relies on, and remove more than half the real false alarms.

## The three left (diagnostics of the third run)

- **S017 (SBI, printed from Safari on iOS):** Apple's print-to-PDF wrote 31 one-page subsets of
  the body font and three of the bold font, which `duplicate_font` read as a font added twice.
  Fixed (21 Nov): when the body font comes as five or more one-page subsets, every font's
  copies are print artefacts. A second font (Helvetica-Bold, 4 spans) on the last page remains.
- **S001 and S026 (PNB, both made by OpenPDF 1.3.32):** the same pattern in both: Helvetica,
  not embedded, on one page, and LiberationSans for 5 spans on the last page. Two genuine
  statements of one bank with the same "anomaly" is the bank's own layout, but no rule from the
  file alone can tell it from an edit. Options: per-bank profiles learned from genuine
  statements (evaluated leaving each statement out), or accept and report.
- **Financial (7 of 19, not fused):** J&K statements printed from iOS leave 46–118 amounts
  unread and 20–67 balance breaks; two Axis statements break in clusters (likely same-day rows
  in a different order). **OCR (8 of 22, not fused):** long statements (650–2,700 rows) keep
  1–26 misreads that no rule explains.

## Bank profiles (21 Nov 2026, option A)

`signals/pdf_structure/profiles.py`: per bank and producing software, the signatures of the
structure findings (check, font families, where in the document: first/last/middle/several
pages; no text) that genuine statements show. A finding whose signature another genuine
statement of the same bank and software also shows is not counted. `eval_real.py` reports the
fused verdict with profiles alongside the plain one, each statement judged against profiles
built from the other statements only (leave-one-out), and writes the profiles
(`bank_profiles_<date>.json`, git-ignored). Expected on the 29 statements: both PNB statements
clear each other; S017, the only Safari print, keeps one finding (weight 0.6), below the
fused threshold on its own. Profiles change nothing on the synthetic test set (its genuine
statements raise no structure findings).
