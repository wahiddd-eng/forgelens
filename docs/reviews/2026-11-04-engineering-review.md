# Engineering review — 4 November 2026

**Scope:** everything built so far: the generator (10 fictional banks), the forgeries (PDF
edits, template rebuilds, laundering), the reader and the three rule-based signals, the
experiment scripts, tests, CI and the v1–v3 results.

**Method:** read every module; ran each signal on the kinds of files real applicants upload
(password-protected, damaged, linearised, digitally signed, tables whose header is printed
only on page 1 or centred over its column); read every kind of forgery back from its PDF and
compared it with its label, for all 10 banks; checked the CI history; installed the package
into a clean Python 3.10 environment and ran the full test suite there; regenerated the full
dataset and results with the fixed code.

**Branch:** `review/engineering-review`.

## Verdict

The foundation is sound. The table reader recovers every value on all 10 layouts, the
running-balance arithmetic is exact, the forgery labels locate every edit to the pixel, and
the tests check behaviour rather than implementation. The problems were at the edges:

- **CI was red** on the latest feature branch, and slow for no benefit.
- **One label bug** affected about 30% of the PDF-edit forgeries.
- **Several false positives** would hit real genuine statements, the most damaging error for
  a tool that may reject a loan applicant. Our synthetic data could not show them, because
  every generated statement repeats a right-aligned table header on every page, and is
  unsigned, unlocked and not linearised.
- **Results were not reproducible or traceable:** the same seed gave different bytes, one
  dataset differed from machine to machine, and summaries did not say which code made them.

All of these are fixed on the branch, and the v4 results replace v3.

## Findings and fixes

Severity: **High** = wrong results, crashes or false positives on real files; **Medium** =
reproducibility, maintainability or evaluation rigour; **Low** = polish.

### Correctness

| # | Sev. | Finding | Evidence | Fix |
| --- | --- | --- | --- | --- |
| 1 | High | Naive `credit_amount` forgeries claimed an inflated `total_credits` that the forged PDF never shows: the forger edits one cell and leaves the summary alone. | Reading the forged PDFs back: summary total ≠ label in 10/10 banks | The new total is claimed only by the consistent variant. `tests/test_labels_match_documents.py` reads back every forgery type for every bank (70 tests). |
| 2 | Medium | Rebuild labels stored summary `old` values unformatted (`22578.94` next to `54,037.94`), had no `old_bbox`, and could "change" the name to the same name. | 36/36 summary edits in the probe | `old` as the bank prints it; `old_bbox: null` (the value was never drawn in the rebuilt file); the name always differs. |
| 3 | Medium | `rebuilt_imitation` labels recorded the *requested* font. If that font is not installed, the PDF silently uses the bank's own font, but the label still says "different font". | Font stacks fall back through fontconfig | Labels record `rendered_fonts` and `font_changed`. |
| 4 | Medium | `forge()` copied the genuine file to the forgery's name before editing, so a failure left an unedited genuine copy named as a forgery. | Code reading | Edits are made in a temporary file, which is moved into place only on success (tested). |
| 5 | Medium | The scripts stopped on the first bad statement (no credits to inflate, layout not readable) and left orphan PDFs. | Code reading | Each item fails on its own and is reported. The generator lists failures in its manifest and exits non-zero. |

### Robustness on real statements

| # | Sev. | Finding | Evidence | Fix |
| --- | --- | --- | --- | --- |
| 6 | High | Statements that print the table header only on page 1 were read only up to the end of page 1, so the financial signal raised six findings on a **genuine** statement. | 15 of 130 rows read | Pages without a header use the columns of the last page that had one. All 10 layouts are tested with the header removed from later pages. |
| 7 | High | Amounts were assigned to the column whose *header label* ends nearest. With labels centred over their columns, as many banks print them, debits and credits went unassigned, giving false findings on genuine statements in 6 of 10 layouts. The same fault made 2 of 300 imitation rebuilds unreadable: a larger font made the WITHDRAWALS label overflow its column. | Found when the v4 run with error handling reported 2 skipped rebuilds | Column edges are measured from the right-aligned amounts under each label, over all pages, with the label edge as the fallback. Tested with centred labels on all 10 layouts and with the overflowing font (7 of these 11 tests fail on the old reader). |
| 8 | High | Password-protected statements, which Indian banks send by default, crashed all three signals (`ValueError: document closed or encrypted`). Damaged, empty or renamed files crashed them with assorted PyMuPDF errors, and one bad file stopped a whole evaluation. | Probe | `forgelens.reader.open_pdf` raises `PasswordRequired` or `UnreadablePDF`. Every signal accepts `password=` and otherwise abstains with `error` set. The evaluation records unreadable files instead of dying. |
| 9 | High | Linearised ("Fast Web View") genuine PDFs were flagged `incremental_update`: they have two `startxref` sections by design. | Ghostscript `-dFastWebView` output flagged | The extra section of a linearised file is not counted. |
| 10 | High | Digitally signed genuine statements would be flagged: signing appends a save section and updates the modification date. | Hand-built signed PDF | One section per signature is allowed, and signed, untouched files are not reported as modified. New checks: `modified_after_signing` (a section after the last signature) and `signature_broken` (byte range no longer matches the file, i.e. re-written after signing). Both are caught when a signed statement is edited (tested). |
| 11 | Medium | The template matcher compared text sizes with exact float equality. | Code reading | 0.15 pt tolerance (imitations differ by 0.3 pt or more). |

### Reproducibility

| # | Sev. | Finding | Evidence | Fix |
| --- | --- | --- | --- | --- |
| 12 | Medium | The same seed gave different PDF bytes on every run. Font subsetting stamps the time of rendering into each embedded font, so a statement dated 2025 carried fonts dated November 2026. | `cmp` of two renders | `SOURCE_DATE_EPOCH` is set to the statement's date while rendering: identical bytes across runs and processes on the same set-up (tested). |
| 13 | Medium | The same seed rendered differently on different machines. Font stacks began with Arial, Times New Roman and Calibri, which exist on a Mac but not on Linux, so a dataset made on Wahid's MacBook would differ from one made on Linux, and template profiles fitted on one would flag statements from the other. | Font stacks | Stacks start with the free metric-compatible fonts (Liberation, Carlito, DejaVu). The PDF's real fonts are recorded in every ground truth and in a generator `manifest.json`, with a warning when a font is missing. Install instructions are in the README. |
| 14 | Medium | Each forgery's seed was drawn from one random sequence in file order, so adding or removing one statement changed every forgery after it. | Code reading | Seeds derive from the run seed and the statement id (`stable_seed`). Tested by forging one bank alone and checking that its labels are identical to the full run. |
| 15 | Low | Generated dates ran past the date the dataset was made: statements up to 5 Nov 2026, forgery edits up to January 2027. A plausibility check on dates would be confounded. | Code reading | Periods end by 30 Jun 2026. |

### Architecture, packaging and CI

| # | Sev. | Finding | Evidence | Fix |
| --- | --- | --- | --- | --- |
| 16 | High | CI failed on `feat/rebuilt-forgeries-template-signal`: a test assumed the Carlito font is installed. | CI run 41877958315 | The test compares with the fonts the PDFs really embed; CI installs the bank fonts. |
| 17 | High | Each CI run spent over 4 minutes installing PyTorch with the full CUDA toolkit (several gigabytes), which no test uses. Ghostscript was not installed, so the laundering tests were silently skipped. | CI logs | Dependencies declared in `pyproject.toml` with `dev`, `ml` and `app` extras. CI installs only `.[dev]`, plus Pango, Ghostscript and the fonts, and runs Python 3.10 and 3.13 with a non-editable install, which also checks that the templates are packaged. `pytest -ra` lists skips. A CI run now takes about 3 minutes instead of 16, with nothing skipped. |
| 18 | Medium | `pip install -e .` installed nothing: the package declared no dependencies. | `pyproject.toml` | Fixed by #17. Verified in a clean Python 3.10 virtual environment. |
| 19 | Medium | Layering: the generator imported the financial signal's reader, the forgery code imported a private function from the structure signal, and the signals imported each other. | Imports | New `forgelens.reader` package (`open_pdf`, `read_cells`, `font_key`, `parse_statement`) used by all of them. The signals are now independent. |
| 20 | Low | The linter version was unpinned, so any ruff release could break CI; ruff 0.16 (installed here) reports rules the code had never been checked against. | Local run | `ruff>=0.16,<0.17`. |

### Evaluation rigour

| # | Sev. | Finding | Fix |
| --- | --- | --- | --- |
| 21 | Medium | No confidence intervals. With 600 forgeries per condition, a recall of 0.76 is ±0.03; the per-variant rates rest on 39–154 files each (±0.08–0.16); and "FPR 0 of 300" still allows up to 1.3%. | 95% Wilson intervals on precision, recall and false-positive rate. |
| 22 | Medium | Localisation was reported as recall only, so a signal pointing at every word on the page would score 100%. | Localisation precision too (share of pointed-at regions that were really edited), per forgery method. |
| 23 | Medium | Summaries did not record which code, library versions or arguments produced them. | Every summary and template-profile file records the git commit (and whether the tree was dirty), Python, PyMuPDF, WeasyPrint and Ghostscript versions, and the command. |
| 24 | Low | v1 and v2 were superseded without a note. | `experiments/results/README.md` indexes every result set and its status. |
| 25 | Low | The scripts, which produce every number in the paper, had no tests. | `tests/test_pipeline_smoke.py` runs generate → forge → rebuild → launder → fit → evaluate → compare on a tiny dataset. |

## Results after the fixes (v4)

Same design as v3 (300 genuine statements, 300 PDF edits, 300 rebuilds, each also reprinted and rasterised; templates fitted on 120 separate statements), regenerated with the fixed code at commit `71f1bfc`. Unreadable files: 0.

Recall on forgeries (95% interval), v3 → v4:

| Condition | Financial | PDF structure | Template | Any signal |
| --- | --- | --- | --- | --- |
| Original | 0.28 → 0.24 [0.20–0.27] | 0.51 → 0.51 [0.47–0.55] | 0.76 → 0.76 [0.73–0.80] | 0.76 → 0.76 [0.73–0.80] |
| Reprinted | 0.28 → 0.24 [0.20–0.27] | 0.55 → 0.55 [0.51–0.59] | 0.75 → 0.76 [0.73–0.79] | 0.76 → 0.76 [0.73–0.80] |
| Rasterised | 0.00 → 0.00 [0.00–0.01] | 0.00 → 0.00 [0.00–0.01] | 0.00 → 0.00 [0.00–0.01] | 0.00 → 0.00 [0.00–0.01] |

False-positive rate on the 300 genuine statements: 0.00 for every signal and condition (upper 95% bound 0.013).

Flag rate of any signal by forgery type (original files), v3 → v4:

| Forgery type | n (v4) | v3 | v4 |
| --- | --- | --- | --- |
| closing_balance | 64 | 100% | 100% |
| credit_amount | 78 | 100% | 100% |
| credit_amount_consistent | 110 | 100% | 100% |
| holder_name | 48 | 100% | 100% |
| rebuilt_exact | 142 | 0% | 0% |
| rebuilt_imitation | 158 | 100% | 100% |

Localisation on the original files (new in v4):

| Signal | Forgeries | Edits | Recall | Regions pointed at | Precision |
| --- | --- | --- | --- | --- | --- |
| PDF structure | pdf_edit | 7281 | 1.00 [1.00–1.00] | 7267 | 1.00 [1.00–1.00] |
| PDF structure | rebuild | 29309 | 0.00 [0.00–0.00] | 75 | 0.00 [0.00–0.05] |
| Template | pdf_edit | 7281 | 0.57 [0.56–0.59] | 4186 | 1.00 [1.00–1.00] |
| Template | rebuild | 29309 | 0.51 [0.51–0.52] | 105913 | 0.14 [0.14–0.14] |

**What the numbers say:**

- **Detection is unchanged.** Financial recall fell from 0.28 to 0.24 only because the mix of
  forgery types changed when forgery seeds started to depend on statement ids. There are 142
  naive edits out of 600 in v4, against 165 in v3. In both runs the financial signal flags
  100% of naive edits and 0% of arithmetic-preserving ones. Cite rates per forgery type,
  not the pooled recall, which depends on the mix.
- **False-positive rate is 0 of 300 on synthetic genuine statements**, which bounds it below
  1.3%. Real statements are the open question (see the recommendations below).
- **Laundering:** reprinting changes nothing, and rasterising defeats all three rule-based
  signals (they abstain). Rasterised files are the image-forensics signal's job (Phase 3).
- **Localisation needed the precision column.** On imitation rebuilds the template signal
  points at every span in the imitation font, so it covers half of the edited values (the
  imitations) at a precision of only 0.14. That is a verdict ("not this bank's system"), not
  a map of the edits. The structure signal's 75 locations on rebuilds are all `₹` signs drawn
  in a fallback font (Inter) because the imitation font has no rupee glyph. That is a real
  forgery cue, but not where the values changed, and it depends on the fonts installed.
- **Exact rebuilds stay undetectable** by any document-based signal (0 of 142), as designed:
  they set the floor that only external verification (for example, account-aggregator data)
  can lift.

## Still open: recommendations, in priority order

These need decisions or data rather than code, so they are not done on this branch.

1. **Measure false positives on real genuine statements early.** FPR = 0 on synthetic data
   only shows that the signals agree with the generator they were designed with. Findings
   6–10 were all false positives that the synthetic data could not reveal. Collect 30–50
   consented real statements from several banks (password-protected, signed and multi-page
   ones included) during Phase 2 rather than Phase 4. Keep them out of the repository.
2. **Build a blind test set.** The same people designed the forgeries and the detectors (for
   example, "fallback font = Helvetica" and "check for non-embedded fonts"). Ask people outside
   the team to forge statements with the tools forgers really use: Acrobat, iLovePDF, Sejda,
   Word's PDF editing, online editors and image editors or AI inpainting. Report on that set
   separately.
3. **Validate signatures cryptographically** (for example with pyHanko) and learn per bank
   whether its statements are always signed. A missing signature on a bank that always signs
   is strong evidence. Ghostscript reprinting removes signatures today without trace.
4. **Do not ship "any signal fires" as the decision rule.** Its false-positive rate grows with
   every signal added: harmless at 0 on synthetic data, not on real data. The Phase 4 fusion
   model must be calibrated on real genuine statements.
5. **Template profiles are tied to the machine's fonts and libraries.** Fit them on the
   machine that renders the evaluation data, and refit whenever fonts or WeasyPrint change.
   The profile file now records its environment.
6. **Parallel generation.** With two CPUs, the v4 pipeline takes about an hour. Phase 2 will
   need thousands of statements, so add `--jobs` to the scripts (the stable per-statement
   seeds already make this safe).
7. **Small reader gaps:** ISO dates (`2025-09-03`), negative amounts in brackets
   (`(1,234.00)`) and left-aligned header labels over narrow amounts are not handled yet.
   None appears in our layouts; real statements may have them.
8. **Progress log:** these items belong in the PROGRESS.md backlog. It was not changed here,
   as agreed.

## How to check this review

```bash
git checkout review/engineering-review
pip install -e ".[dev]"
ruff check . && pytest -ra        # 390 tests, about 2 minutes
```

The probes behind the findings are reproduced by the tests:
`test_reader_robustness.py` (findings 6–10), `test_labels_match_documents.py` (1–3),
`test_pdf_edit.py` (4 and the font fallback), `test_evaluation_and_reproducibility.py`
(12, 14, 15, 21, 22) and `test_pipeline_smoke.py` (5, 14, 23, 25).
