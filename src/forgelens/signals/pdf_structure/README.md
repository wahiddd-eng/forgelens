# PDF-structure signal

Looks for traces that editing leaves inside the PDF file. It reads only the file, so it works on any statement.

| Check | Fires when |
| --- | --- |
| `incremental_update` | The file has more than one `startxref`: an update was appended after creation |
| `modified_after_creation` | The modification date is later than the creation date |
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

Image-only PDFs (scans) have no text layer; the signal then returns a neutral score of 0.5.

**Limitation:** these traces depend on the editing tool. Re-rendering an edited statement to a fresh PDF removes most of them, so the image and template signals are still needed.
