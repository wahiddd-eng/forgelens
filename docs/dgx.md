# Working on the SRMIST DGX A100

One A100 (40 GB) and 500 GB are allotted to ForgeLens, reachable only from the one
registered laptop on the campus Wi-Fi. The account name and first password are in the
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
nvidia-smi                   # if all GPUs are listed, ask which index is ours
echo 'export CUDA_VISIBLE_DEVICES=<index>' >> ~/.bashrc && source ~/.bashrc
df -h ~                      # where the 500 GB is
```

## Getting the code and data onto the server

The repository is private, so either clone it with a read-only GitHub personal access
token, or copy it from the laptop:

```bash
rsync -av --exclude data --exclude .venv ~/forgelens <user>@172.16.0.32:~/
```

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

## Rules that affect planning

- Allocations last 20 days; request renewal at least 4 days before expiry. A new form is
  needed after 3 months.
- The server is rebooted weekly and nothing is backed up: save checkpoints often, use
  `--resume`, and copy results back to the laptop after each run.
- About 400 GPU-hours on one GPU is roughly 17 days of continuous use, so debug on the home
  PC or a rented GPU and use the DGX for full runs only.
