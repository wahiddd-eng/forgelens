# Forgery

Scripts that turn genuine generated statements into labelled forgeries.

## PDF-edit forgeries (`pdf_edit.py`)

Imitates a forger editing the PDF directly: the original value is painted over with the cell's background colour, the underlying text is removed, and the new value is typed at the same position and size.

| Variant | What changes | Arithmetic still valid? |
| --- | --- | --- |
| `credit_amount` | One credit (salary or transfer preferred) is inflated | No: the running balance breaks |
| `credit_amount_consistent` | The credit, every later balance, total credits and closing balance | **Yes** |
| `closing_balance` | Closing balance in the summary and in the last row | No |
| `holder_name` | Account holder's name | Yes (figures untouched) |

A forged PDF is written to a temporary file and moved into place only when complete, so a failure never leaves a copy of the genuine file under a forgery's name. The scripts derive each forgery's seed from the run seed and the statement's id (`forgelens.utils.stable_seed`), so adding or removing statements does not change the other forgeries.

Each forgery also varies in how it was made, which the PDF-structure signal can pick up:

- **Font strategy:** `matched` (same font family as the original, nearly invisible) or `fallback` (Helvetica, as a careless forger would use). If the matching font is not installed, `fallback` is used and the label says so.
- **Save mode:** `incremental` (the original file plus an update section, two `%%EOF` markers) or `rewrite` (a fully rewritten file).
- **Metadata:** the modification date is updated in some forgeries and left alone in others.

## Labels

Each forged PDF gets a JSON label containing:

- `label: "forged"`, the `source_statement_id` and how the forgery was made (`forgery`);
- every edit: field, row, page, old and new text, the original and new text boxes and the `mask_bbox` (both boxes combined, in PDF points);
- the values the forged document now claims (`transactions`, `closing_balance`, `total_credits`, `customer`). A naive `credit_amount` edit leaves the summary untouched, so its `total_credits` stays the original value; `tests/test_labels_match_documents.py` reads every kind of forgery back and checks its label.

`write_masks()` draws binary PNG masks (255 = edited) at any DPI. They match pages rendered with `page.get_pixmap(dpi=...)` pixel for pixel.

## Usage

```bash
python scripts/generate_statements.py --count 100 --seed 0 --out data/synthetic/genuine
python scripts/forge_pdf_edits.py --genuine data/synthetic/genuine/himalaya_national \
    --out data/synthetic/forged/pdf_edit --per-statement 2 --seed 0 --masks --dpi 150
```

## Template-rebuilt forgeries (`rebuild.py`)

The forger regenerates the whole statement with better numbers instead of editing the PDF. Every salary credit (or incoming transfer, else the largest credit) is inflated by 1.4–2.5×, and every later balance, the totals and the closing balance are recomputed, so the arithmetic is fully consistent. In 30% of cases the holder's name is also replaced.

| Variant | How it is rendered | Detectable from the document? |
| --- | --- | --- |
| `rebuilt_exact` | The bank's real template and settings (insider or perfect copy) | No: needs an external check |
| `rebuilt_imitation` | An imitation: different font, text size ±0.3–0.8 pt, often a different "Creator" | Yes, by the template signal |

Labels list every changed cell with its position in the new PDF, so masks work as for PDF edits. `old` is the value as the genuine statement printed it; `old_bbox` is `null` because the original value was never drawn in the rebuilt file. Imitation labels also record `rendered_fonts`: if the imitation font is not installed, the PDF may fall back to the bank's own font, and `font_changed` says whether that happened.

```bash
python scripts/forge_rebuild.py --genuine data/synthetic/genuine --out data/synthetic/forged/rebuild --masks
```

## Laundering (`launder.py`)

Re-saves a genuine or forged statement the way people do, to strip file-level traces:

| Method | What it does | Text layer |
| --- | --- | --- |
| `reprint` | Ghostscript re-distil, like "Print to PDF": one save section, one content stream per page, all fonts embedded, equal creation and modification dates | Kept |
| `raster` | Every page rendered to a JPEG and wrapped in a new PDF, like a screenshot or scan | Removed |

Apply it to genuine statements too, so a detector cannot learn "re-saved means forged". Page geometry is unchanged, so masks stay valid (`--masks` rewrites them for the new file names).

```bash
# macOS: brew install ghostscript
python scripts/launder_pdfs.py --input data/synthetic/forged/pdf_edit \
    --out data/synthetic/forged/pdf_edit_reprint --method reprint --masks
```

Coming next: image-level edits (copy-paste and splicing), AI inpainting and fully generated fakes — these run on the GPU machine.
