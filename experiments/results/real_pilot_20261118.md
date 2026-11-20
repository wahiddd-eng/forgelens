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
