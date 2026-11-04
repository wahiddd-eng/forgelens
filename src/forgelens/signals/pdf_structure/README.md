# PDF-structure signal

Looks for traces that editing leaves inside the PDF file. It reads only the file, so it works on any statement.

| Check | Fires when |
| --- | --- |
| `incremental_update` | The file has more save sections (`startxref`) than a genuine file can explain: an update was appended after creation. One extra section is allowed for a linearised ("Fast Web View") file and one per digital signature |
| `modified_after_signing` | A save section follows the last digital signature (a Document Security Store added by a validator is allowed) |
| `signature_broken` | A signature's byte range no longer matches the file: it was re-written after signing |
| `modified_after_creation` | The modification date is later than the creation date (not reported for signed files that were not changed after signing) |
| `non_embedded_font` | Some text uses a non-embedded standard font (e.g. Helvetica) while the rest is embedded |
| `duplicate_font` | The same font family and style is embedded twice under different names |
| `extra_content_streams` | Some pages have more content streams than the others |
| `font_anomaly` | Individual spans use a font the rest of the document does not; returned **with positions** |

```python
from forgelens.signals.pdf_structure import analyze_pdf

report = analyze_pdf("statement.pdf")
report.suspicious     # True if any check fired
report.score          # 0–1, combining the weights of the checks that fired
report.locations()    # [{"page", "bbox", "text", "font"}] — where the edits probably are
report.features()     # numeric features for the fusion classifier
```

Image-only PDFs (scans) have no text layer; the signal then abstains with a neutral score of 0.5. So does a locked file without its password (`analyze_pdf(path, password=...)`) or a damaged file; `report.error` says why.

Signatures are checked for structure only. Whether a signature is cryptographically valid and was made by the bank needs a validator such as pyHanko with the bank's certificate; that is future work.

**Limitation:** these traces depend on the editing tool. Re-rendering an edited statement to a fresh PDF removes most of them, so the image and template signals are still needed.
