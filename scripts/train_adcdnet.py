"""Fine-tune ADCD-Net on statement pages (plus DocTamper), starting from the released weights.

The training objective, crops and augmentation are upstream's (``third_party/ADCD-Net``); what
changes is the data: crops of rendered statement pages (with and without edits) mixed with
DocTamper's training set. See ``forgelens.signals.image.training``.

    # one GPU
    CUDA_VISIBLE_DEVICES=3 python scripts/train_adcdnet.py --config configs/adcdnet_eval.yaml \\
        --data ~/forgelens-data/synthetic_v4/genuine_raster ~/forgelens-data/synthetic_v4/forged_image \\
        --tag ft1

    # two GPUs (picked with free_gpus.sh)
    CUDA_VISIBLE_DEVICES=3,6 torchrun --standalone --nproc_per_node 2 scripts/train_adcdnet.py ...

Writes ``<out>/train_<tag>/``: ``ckpt/Step<N>_Score<F1>.pth`` (the 3 newest and the best are
kept; the score is F1 on edited validation pages), ``log.jsonl`` (losses and validation),
and renders pages once into ``--cache`` (reused by later runs). ``--resume`` continues from the
newest checkpoint.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from forgelens.signals.image import adcdnet

REPO = Path(__file__).resolve().parents[1]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--config", type=Path, required=True,
                   help="the eval_adcdnet.py YAML (ckpt, docres, doctamper_root, ocr_root)")
    p.add_argument("--data", type=Path, nargs="+", required=True,
                   help="folders of statement PDFs + labels (searched recursively)")
    p.add_argument("--tag", required=True)
    p.add_argument("--out", type=Path, default=REPO / "experiments" / "checkpoints",
                   help="runs go in <out>/train_<tag> (the default is backed up by backup.py)")
    p.add_argument("--cache", type=Path, default=Path("~/forgelens-data/page_cache"),
                   help="rendered pages, shared by runs (kept out of the backups)")
    p.add_argument("--exclude-banks", nargs="+", default=[], metavar="BANK",
                   help="leave these banks out of training and validation (to test them as "
                        "unseen layouts later)")
    p.add_argument("--val-fraction", type=float, default=0.2,
                   help="share of source statements held out for validation")
    p.add_argument("--dpi", type=int, default=150)
    p.add_argument("--init", type=Path, help="start from this checkpoint (default: config ckpt)")
    p.add_argument("--resume", action="store_true")
    g = p.add_argument_group("training")
    g.add_argument("--steps", type=int, default=20000, help="optimiser steps")
    g.add_argument("--batch-size", type=int, default=8, help="per GPU")
    g.add_argument("--accum", type=int, default=2, help="gradient accumulation")
    g.add_argument("--crop", type=int, default=256, help="training crop size (upstream: 256)")
    g.add_argument("--lr", type=float, default=5e-5)
    g.add_argument("--min-lr", type=float, default=1e-6)
    g.add_argument("--warmup", type=int, default=200)
    g.add_argument("--doctamper-share", type=float, default=0.3,
                   help="share of crops from DocTamper's training set (0 to leave it out)")
    g.add_argument("--edited-share", type=float, default=0.6,
                   help="share of statement crops that contain an edit")
    g.add_argument("--workers", type=int, default=6, help="data-loading processes per GPU")
    g.add_argument("--device", default="cuda", help="cuda, or cpu for a test run")
    g = p.add_argument_group("validation and saving")
    g.add_argument("--val-every", type=int, default=1000)
    g.add_argument("--val-pages", type=int, default=300)
    g.add_argument("--val-batch", type=int, default=16, help="tiles per forward pass")
    g.add_argument("--val-doctamper", type=int, default=300, help="FCD images (0 to skip)")
    g.add_argument("--keep", type=int, default=3)
    g.add_argument("--log-every", type=int, default=50)
    return p.parse_args(argv)


def lr_at(step: int, args) -> float:
    if step < args.warmup:
        return args.lr * (step + 1) / args.warmup
    t = (step - args.warmup) / max(1, args.steps - args.warmup)
    return args.min_lr + 0.5 * (args.lr - args.min_lr) * (1 + math.cos(math.pi * min(t, 1.0)))


def prune(ckpt_dir: Path, keep: int) -> None:
    """Keep the ``keep`` newest checkpoints and the best-scoring one."""
    def step_of(p):
        return int(p.stem.split("_")[0][4:])

    def score_of(p):
        return float(p.stem.split("_Score")[1])

    files = sorted(ckpt_dir.glob("Step*_Score*.pth"), key=step_of)
    if not files:
        return
    best = max(files, key=score_of)
    for f in files[:-keep]:
        if f != best:
            f.unlink()


def main(argv=None) -> int:
    args = parse_args(argv)
    import torch
    import torch.distributed as dist
    import yaml

    distributed = "WORLD_SIZE" in os.environ and int(os.environ["WORLD_SIZE"]) > 1
    rank = int(os.environ.get("RANK", "0"))
    local = int(os.environ.get("LOCAL_RANK", "0"))
    world = int(os.environ.get("WORLD_SIZE", "1"))
    if distributed:
        dist.init_process_group("nccl")
    cuda = args.device != "cpu"
    if cuda and not torch.cuda.is_available():
        print("CUDA is not available: pick a GPU with free_gpus.sh first", file=sys.stderr)
        return 1
    if cuda:
        torch.cuda.set_device(local)
    device = f"cuda:{local}" if cuda else "cpu"
    main_proc = rank == 0

    def log(msg):
        if main_proc:
            print(msg, flush=True)

    cfg_yaml = {k.replace("-", "_"): v for k, v in yaml.safe_load(args.config.read_text()).items()}
    paths = adcdnet.Paths(upstream=REPO / "third_party" / "ADCD-Net",
                          ckpt=args.init or cfg_yaml["ckpt"], docres=cfg_yaml["docres"],
                          doctamper_root=cfg_yaml.get("doctamper_root"),
                          ocr_root=cfg_yaml.get("ocr_root"), qt_path=cfg_yaml.get("qt_path"))
    cfg = adcdnet.configure(paths, adcdnet.Settings())
    cfg.img_size = args.crop  # read by upstream's augmentation when the datasets are built
    from forgelens.signals.image import training

    run = args.out.expanduser() / f"train_{args.tag}"
    ckpt_dir = run / "ckpt"
    cache = args.cache.expanduser()
    if main_proc:
        ckpt_dir.mkdir(parents=True, exist_ok=True)
        (run / "args.json").write_text(json.dumps(vars(args), indent=2, default=str))
        log(f"==> page cache {cache}")
        training.build_page_cache(args.data, cache, args.dpi, args.val_fraction, log=log)
    if distributed:
        dist.barrier()
    index = json.loads((cache / "index.json").read_text())
    # Every page in the cache is used; --data only decides what gets added to it.
    if args.exclude_banks:
        index = [e for e in index if training.bank_of(e) not in set(args.exclude_banks)]
        log(f"    leaving out banks: {', '.join(args.exclude_banks)}")
    train_pages = [e for e in index if e["split"] == "train"]
    val_pages = [e for e in index if e["split"] == "val"]
    log(f"    train: {len(train_pages)} pages ({sum(e['edited'] for e in train_pages)} edited); "
        f"val: {len(val_pages)} pages ({sum(e['edited'] for e in val_pages)} edited)")

    samples = args.steps * args.accum * args.batch_size  # per process
    pages = training.PageCrops(cache, train_pages, samples, args.edited_share)
    doctamper = None
    if args.doctamper_share > 0:
        from ds import TrainDs

        doctamper = TrainDs()
        doctamper.S = 25 * doctamper.T  # JPEG quality from 75 up, as late in upstream training
    data = training.Mixed(pages, doctamper, args.doctamper_share)
    loader = torch.utils.data.DataLoader(data, batch_size=args.batch_size,
                                         num_workers=args.workers, worker_init_fn=training.worker_init,
                                         persistent_workers=args.workers > 0, drop_last=True)

    model, _ = adcdnet.load_model(paths, device)
    model.train()
    optim = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=cfg.weight_decay)
    scaler = torch.amp.GradScaler(enabled=cuda)
    step = 0
    if args.resume:
        found = sorted(ckpt_dir.glob("Step*_Score*.pth"), key=lambda p: int(p.stem.split("_")[0][4:]))
        if found:
            state = torch.load(found[-1], map_location="cpu", weights_only=False)
            model.load_state_dict(state["model"])
            optim.load_state_dict(state["optimizer"])
            scaler.load_state_dict(state["scaler"])
            step = state["step"]
            log(f"==> resumed from {found[-1].name}")
    net = torch.nn.parallel.DistributedDataParallel(model, device_ids=[local] if cuda else None,
                                                    find_unused_parameters=True) \
        if distributed else model
    losses = training.Losses()

    def validate():
        result = {"step": step}
        if main_proc:
            v = training.validate_pages(model, cache, val_pages, device, args.val_pages,
                                         args.val_batch)
            result.update({"val_f1": v.f1, "val_auc": v.auc, "val_clean_area": v.clean_area,
                           "val_pages": v.pages})
            if args.val_doctamper and paths.doctamper_root is not None:
                result["fcd_f1"] = training.validate_doctamper(model, "FCD", device,
                                                               args.val_doctamper)
            log("    validation: " + ", ".join(f"{k} {v:.4f}" if isinstance(v, float) else
                                               f"{k} {v}" for k, v in result.items()))
            with open(run / "log.jsonl", "a") as f:
                f.write(json.dumps({"kind": "val", **result}) + "\n")
        if distributed:
            dist.barrier()
        return result

    if step == 0:
        log("==> validating the starting weights")
        validate()

    log(f"==> training {args.steps} steps on {world} GPU(s), {args.batch_size} x {args.accum} "
        f"crops per step per GPU, from step {step}")
    running: dict[str, float] = {}
    start, seen = time.time(), 0
    batches = iter(loader)
    while step < args.steps:
        for g in optim.param_groups:
            g["lr"] = lr_at(step, args)
        optim.zero_grad(set_to_none=True)
        for _ in range(args.accum):
            items = next(batches)
            img, dct, qt, mask, ocr, is_align = (items[k].to(device) for k in
                                                 ("img", "dct", "qt", "mask", "ocr_mask",
                                                  "is_align"))
            with torch.autocast(device_type="cuda", dtype=torch.float16, enabled=cuda):
                outputs = net(img, dct, qt, mask, ocr, is_train=True)
            parts = losses(outputs, img, mask, is_align)
            scaler.scale(parts["total"] / args.accum).backward()
            for k, v in parts.items():
                running[k] = running.get(k, 0.0) + float(v) / args.accum
            seen += img.shape[0]
        scaler.unscale_(optim)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scaler.step(optim)
        scaler.update()
        step += 1

        if step % args.log_every == 0 and main_proc:
            rate = seen * world / (time.time() - start)
            avg = {k: v / args.log_every for k, v in running.items()}
            log(f"step {step}/{args.steps} lr {lr_at(step, args):.2e} "
                + " ".join(f"{k} {v:.4f}" for k, v in avg.items())
                + f" | {rate:.1f} crops/s")
            with open(run / "log.jsonl", "a") as f:
                f.write(json.dumps({"kind": "train", "step": step, **avg, "crops_per_s": rate})
                        + "\n")
            running = {}
        if step % args.val_every == 0 or step == args.steps:
            result = validate()
            if main_proc:
                path = ckpt_dir / f"Step{step}_Score{result['val_f1']:.4f}.pth"
                tmp = path.with_suffix(".tmp")
                torch.save({"model": model.state_dict(), "optimizer": optim.state_dict(),
                            "scaler": scaler.state_dict(), "step": step, "validation": result,
                            "args": json.loads((run / "args.json").read_text())}, tmp)
                tmp.replace(path)
                prune(ckpt_dir, args.keep)
    log("==> done")
    if distributed:
        dist.destroy_process_group()
    return 0


if __name__ == "__main__":
    sys.exit(main())
