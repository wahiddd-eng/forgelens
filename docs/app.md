# The ForgeLens web app

Two views in one page, served by `python -m forgelens.app.server`:

- **Examine a statement.** Upload a PDF, a screenshot or a photo (optionally with the bank's
  name and the PDF's password). ForgeLens runs every check this machine has, gives a verdict,
  and shows each page with the places the checks marked. The lamp button darkens the page so
  marked places, and the image model's heat map, glow.
- **Project results.** The recorded results: which check catches which forgery, what each check
  adds, phone copies, real statements, the image models and the reproduction of ADCD-Net. The
  figures come from `src/forgelens/app/static/results.json`, each with the result file it was
  taken from (`tests/test_app.py` checks them against those files).

What runs depends on what the machine has:

| Check | Laptop | DGX |
| --- | --- | --- |
| Arithmetic in the text, PDF structure | yes | yes |
| Bank layout (the ten fictional banks) | with `--templates` | with `--templates` |
| Arithmetic on the page image (EasyOCR) | if installed | yes |
| Image model with heat maps | no | with `--image-config` |
| Combined score and false-alarm lines | no | with `--fusion` |
| Bank profiles from genuine statements | no | with `--profiles` |

Without a fusion model the verdict says which checks found evidence and says the combined score
runs on the GPU server. On a PDF with a text layer the image model and OCR arithmetic are shown
but not counted, as in evaluation (`scripts/eval_real.py`).

## On your laptop

```bash
pip install -r requirements-app.txt
PYTHONPATH=src python -m forgelens.app.server --templates experiments/templates_v4.json \
    --no-ocr --device cpu
```

Open <http://localhost:8000>. Four fictional samples are bundled (`static/samples.json`, made by
`scripts/make_app_samples.py`), so the page is useful even before you upload anything.

## On the DGX, with every check

In the DGX tab (the prompt must show `(forgelens)`), on a free GPU:

```bash
cd ~/forgelens && git pull
source ~/venvs/forgelens/bin/activate
pip install -r requirements-app.txt
CUDA_VISIBLE_DEVICES=0 python -m forgelens.app.server \
    --fusion experiments/results/fusion_test-ft4-real/model.pkl \
    --image-config configs/adcdnet_ft4.yaml \
    --templates experiments/templates_v4.json
```

That is the configuration measured on the real statements (run 3). After run 4, add
`--profiles experiments/results/bank_profiles_<date>.json`; once `eval_real.sh` has been run with
`MODEL=ft6`, use `fusion_test-ft6-real/model.pkl` and `configs/adcdnet_ft6.yaml`.

Then, in a Mac tab, open a tunnel and leave it open:

```bash
ssh -L 8000:localhost:8000 srmist32@172.16.0.32
```

and open <http://localhost:8000> on the Mac. Stop the server with Ctrl-C in the DGX tab.

To bundle samples that include the image model's heat maps and the combined score, run on the
DGX:

```bash
python scripts/make_app_samples.py --device cuda --ocr \
    --fusion experiments/results/fusion_test-ft4-real/model.pkl \
    --image-config configs/adcdnet_ft4.yaml
```

## Privacy

- The server listens on the machine itself only (`127.0.0.1`); from the Mac it is reached
  through the SSH tunnel, so an upload travels encrypted.
- An upload is written to a private temporary folder, examined, and the folder deleted before
  the answer is sent, also when the examination fails. The access log is off and nothing about
  the file is logged. The password is used to open the file and then dropped.
- The page shows the uploaded statement back to the person who uploaded it and nothing is kept,
  so a real statement can be examined this way under the rule for real statements (deleted right
  after testing). Do not take screenshots of a real statement's result for the paper or slides.
- The bundled samples are fictional statements from ForgeLens's generator.
