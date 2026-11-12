# Working on the SRMIST DGX A100

Up to two A100s (40 GB each), whichever are free, and 500 GB are allotted to ForgeLens,
reachable only from the one registered laptop on the campus Wi-Fi. The account name and first password are in the
Centre for AI's email to Dr. Gopinath; never put them in this repository.

## Before the first login

1. On the laptop, turn off **Private Wi-Fi address** for the campus network (System
   Settings → Wi-Fi → Details…), so the address you register is the one the Mac uses.
2. Raise a ticket with ITKM at sd.srmist.edu.in, with the laptop's MAC address
   (`networksetup -getmacaddress en0`), its IP on the campus Wi-Fi
   (`ipconfig getifaddr en0`; ask ITKM to reserve it for this MAC) and the approval email
   attached.
3. Wait until ITKM confirms that Wi-Fi access is enabled.

## First login

```bash
ssh <user>@172.16.0.32
passwd                       # replace the issued password
exit
ssh-keygen -t ed25519        # on the laptop, if you have no key yet
ssh-copy-id <user>@172.16.0.32
```

Then, on the server:

```bash
nvidia-smi                   # all 8 GPUs are listed; most are in use by other projects
df -h ~                      # where the 500 GB is
```

## Choosing GPUs

All eight GPUs are visible, and we may use at most two, whichever are free. Do not fix GPU
numbers in `~/.bashrc`; pick free ones when each job starts:

```bash
export CUDA_VISIBLE_DEVICES=$(bash scripts/free_gpus.sh 2) || exit 1   # two free GPUs
export CUDA_VISIBLE_DEVICES=$(bash scripts/free_gpus.sh 2 --min 1)     # two, or one if that is all
export CUDA_VISIBLE_DEVICES=$(bash scripts/free_gpus.sh 2 --wait)      # wait until two are free
```

A GPU counts as free when under 1000 MiB of its memory is used and it is under 10% busy.
Two evaluation runs can share the two GPUs (one each, with different `--tag`s); training
uses both through upstream's multi-GPU support.

## Getting the code and data onto the server

The server reaches GitHub, Hugging Face and PyPI, and the repository is public, so clone it
there directly (and never commit private data to it):

```bash
git clone --recurse-submodules https://github.com/wahiddd-eng/forgelens.git ~/forgelens
```

Download public datasets on the server too (AIForge-Doc from Hugging Face, with your token in
`~/.cache/huggingface`, not in the repository).

Copy datasets and checkpoints the same way (`rsync -av --partial --progress`, which can
resume an interrupted copy). **Real bank statements never go on the DGX**: it is shared and
has no backups.

## Environment

```bash
cd ~/forgelens && bash scripts/setup_dgx.sh
```

It installs Python 3.10.14 with pyenv, a virtual environment in `~/venvs/forgelens`,
PyTorch 2.3.0 (CUDA 12.1), ForgeLens and the ADCD-Net packages, builds `jpeg2dct`
(compiling libjpeg-turbo itself when the system lacks it; no sudo needed), checks the GPU
and runs the ADCD-Net pre-flight check. It is safe to run again, and logs to
`~/forgelens_setup.log`. If pip cannot reach the internet, download the wheels elsewhere
(see `requirements-adcdnet.txt`) and run it with `WHEELS=/path/to/wheels`.

## Running jobs

VS Code Remote-SSH and Jupyter are fine for editing and quick checks, but a notebook stops
when VS Code disconnects. Start every long job in tmux:

```bash
tmux new -s eval
source ~/venvs/forgelens/bin/activate
python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --resume
# detach: Ctrl-b d      later: tmux attach -t eval
```

## Backups

Nothing on the DGX is backed up, so copy results, logs and checkpoints off it while jobs run.
`scripts/backup.py` sends what changed to a **private** Hugging Face repository (it refuses a
public one), every 30 minutes by default. Set it up once:

```bash
huggingface-cli login       # paste a write token; it stays in ~/.cache/huggingface
echo 'export FORGELENS_BACKUP=hf:<hf-user>/forgelens-dgx-backup' >> ~/.bashrc
```

Then wrap each job, which backs up during the job and once more when it ends, even if it
fails:

```bash
bash scripts/with_backup.sh python scripts/eval_adcdnet.py --config configs/adcdnet_eval.yaml --tag dgx --resume
BACKUP_ARGS="--source adcd=~/forgelens-data/exp_out" bash scripts/with_backup.sh <training command>
```

It backs up `experiments/results`, `experiments/logs` and `experiments/checkpoints` (add
folders with `--source name=path`), keeps the 3 newest checkpoints per folder plus the
best-scoring one, never deletes a backed-up file because it vanished on the DGX, and refuses
PDFs and anything under `data/` or `real*` folders. Get everything back with
`python scripts/backup.py restore --dest $FORGELENS_BACKUP --to ~/restored`. Log:
`~/forgelens_backup.log`.

## Rules that affect planning

- Allocations last 20 days; request renewal at least 4 days before expiry. A new form is
  needed after 3 months.
- The server is rebooted weekly and nothing is backed up: save checkpoints often, use
  `--resume`, and copy results back to the laptop after each run.
- About 400 GPU-hours is roughly 8–9 days of continuous use on two GPUs (17 on one), so
  debug on the home PC or a rented GPU and use the DGX for full runs only.
