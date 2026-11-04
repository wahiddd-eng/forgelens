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

Each forgery also varies in how it was made, which the PDF-structure signal can pick up:

- **Font strategy:** `matched` (same font family as the original, nearly invisible) or `fallback` (Helvetica, as a careless forger would use). If the matching font is not installed, `fallback` is used and the label says so.
- **Save mode:** `incremental` (the original file plus an update section, two `%%EOF` markers) or `rewrite` (a fully rewritten file).
- **Metadata:** the modification date is updated in some forgeries and left alone in others.

## Labels

Each forged PDF gets a JSON label containing:

- `label: "forged"`, the `source_statement_id` and how the forgery was made (`forgery`);
- every edit: field, row, page, old and new text, the original and new text boxes and the `mask_bbox` (both boxes combined, in PDF points);
- the values the forged document now claims (`transactions`, `closing_balance`, `total_credits`, `customer`).

`write_masks()` draws binary PNG masks (255 = edited) at any DPI. They match pages rendered with `page.get_pixmap(dpi=...)` pixel for pixel.

## Usage

```bash
python scripts/generate_statements.py --count 100 --seed 0 --out data/synthetic/genuine
python scripts/forge_pdf_edits.py --genuine data/synthetic/genuine/himalaya_national \
    --out data/synthetic/forged/pdf_edit --per-statement 2 --seed 0 --masks --dpi 150
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
