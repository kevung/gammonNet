#!/usr/bin/env python3
"""T72 — distillation 0-ply with a ranking term between sibling plays.

## The question

`docs/mesures/2026-10-15-T72-courbe-volume-distillation.md`: a student of the
teacher's own shape plateaus at 0.00797 per contested T70 decision against the
teacher's 0.00266, while its mean absolute gap to the teacher's outputs is down
to 0.002. Capacity is not what is missing. The hypothesis tested here: a
pointwise objective spends its accuracy on every row alike, whereas a decision
only needs the ORDER of the plays of one roll -- and a 0.002 error is enough to
swap two siblings a few hundredths apart.

## Objective

    loss = BCE(student, teacher)                        (rows drawn uniformly,
                                                         exactly the volume
                                                         trainer's objective)
         + lambda * KL(softmax(s_teacher / T) || softmax(s_student / T))
                                                        (whole decisions drawn
                                                         uniformly)

`s` is the MOVER's cubeless equity of a play. A label is the teacher's
evaluation of the child position, seen by the player on roll in it -- the
opponent -- so `s = -equity(label)`; the best play has the lowest label
equity. `lambda = 0` is the volume trainer's recipe, run by the same code: the
ablation is one flag.

Decisions come from the `decisions` field of `tools/build_distill_corpus.py`
parts (rows of one decision are contiguous). A decision cut by a part
boundary is kept as the partial group present in the part; groups of one row
carry no order and are left out of the ranking term.

## What is reported, and what is not

Hold-out: BCE and |gap| as before, plus the 0-ply REGRET -- the teacher's
equity lost by playing the student's favourite among the siblings instead of
the teacher's, averaged over hold-out decisions. It is a cheap compass, not a
strength: the verdict is `bench/measure_t70.py` on the arbitrated registry,
paired against the baseline (`bench/paired_dumps_t70.py`).

Usage:
    python tools/distill_rank_t72.py --corpus build/t72-rang-corpus \\
        --rows 51200000 --shape 256,128,64 --rank-weight 1 --temperature 0.02 \\
        --schedule cosine --max-epochs 1000 --out models/t72r_cible_l1_t02.bin
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from distill_volume_t72 import (  # noqa: E402
    build, export, macs, read_back, select_parts, sha256, value_table,
)


def load_grouped(parts: list[Path], table: np.ndarray, limit: int | None = None):
    """Parts -> (uint8 codes, float32 labels, int64 group starts, int64 sizes).

    Groups are maximal runs of one `decisions` value inside one part, of at
    least two rows, wholly inside the first `limit` rows. Refuses a part
    without the field rather than guessing its boundaries.
    """
    codes, labels, starts, sizes = [], [], [], []
    offset = 0
    for part in parts:
        with np.load(part) as z:
            if "decisions" not in z.files:
                raise SystemExit(f"{part}: pas de champ `decisions` — corpus d'avant T72-rang")
            own = z["values"]
            index = np.searchsorted(table, own)
            if not np.array_equal(table[index], own):
                raise SystemExit(f"{part}: valeur absente de la table globale")
            codes.append(index.astype(np.uint8)[z["codes"]])
            labels.append(z["labels"])
            s, n = group_bounds(z["decisions"])
            starts.append(s + offset)
            sizes.append(n)
            offset += z["labels"].shape[0]
    x, y = np.concatenate(codes), np.concatenate(labels)
    s, n = np.concatenate(starts), np.concatenate(sizes)
    if limit is not None:
        x, y = x[:limit], y[:limit]
        keep = s + n <= limit
        s, n = s[keep], n[keep]
    keep = n >= 2
    return x, y, s[keep], n[keep]


def group_bounds(decisions: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Runs of equal consecutive values -> (start, length), all runs."""
    if decisions.size == 0:
        return np.zeros(0, np.int64), np.zeros(0, np.int64)
    change = np.flatnonzero(np.diff(decisions)) + 1
    starts = np.concatenate([[0], change]).astype(np.int64)
    ends = np.concatenate([change, [decisions.size]]).astype(np.int64)
    return starts, ends - starts


def mover_equity(probs):
    """Cubeless equity of the MOVER from the child's five probabilities.

    The child is seen by its player on roll -- the opponent -- hence the sign.
    Works on numpy arrays and torch tensors alike (last axis = 5 outputs).
    """
    w, wg, wb, lg, lb = (probs[..., i] for i in range(5))
    return -(2.0 * w - 1.0 + wg + wb - lg - lb)


def gather_groups(torch, starts, sizes, chosen):
    """Row indices of the chosen groups, and each row's group number 0..G-1."""
    n = sizes[chosen]
    segment = torch.repeat_interleave(torch.arange(chosen.numel(), device=n.device), n)
    first = torch.cumsum(n, 0) - n
    within = torch.arange(int(n.sum()), device=n.device) - first[segment]
    return starts[chosen][segment] + within, segment


def segment_log_softmax(torch, scores, segment, groups: int):
    """log softmax of `scores` within each segment."""
    top = torch.full((groups,), -torch.inf, device=scores.device, dtype=scores.dtype)
    top = top.scatter_reduce(0, segment, scores, reduce="amax", include_self=True)
    shifted = scores - top[segment]
    total = torch.zeros(groups, device=scores.device, dtype=scores.dtype)
    total = total.index_add(0, segment, torch.exp(shifted))
    return shifted - torch.log(total)[segment]


def rank_loss(torch, student_probs, teacher_probs, segment, groups: int, temperature: float):
    """Mean over groups of KL(teacher || student) on the mover's equities / T."""
    log_p = segment_log_softmax(torch, mover_equity(teacher_probs) / temperature, segment, groups)
    log_q = segment_log_softmax(torch, mover_equity(student_probs) / temperature, segment, groups)
    per_row = torch.exp(log_p) * (log_p - log_q)
    return per_row.sum() / groups


def regret(torch, student_probs, teacher_probs, segment, groups: int):
    """Teacher equity lost by the student's favourite, summed over groups."""
    s = mover_equity(student_probs)
    t = mover_equity(teacher_probs)
    best_t = torch.full((groups,), -torch.inf, device=t.device, dtype=t.dtype)
    best_t = best_t.scatter_reduce(0, segment, t, reduce="amax", include_self=True)
    best_s = torch.full((groups,), -torch.inf, device=s.device, dtype=s.dtype)
    best_s = best_s.scatter_reduce(0, segment, s, reduce="amax", include_self=True)
    # The student's favourite: the first row of its group reaching its max.
    is_top = s == best_s[segment]
    rows = torch.arange(s.numel(), device=s.device)
    first = torch.full((groups,), s.numel(), device=s.device, dtype=torch.long)
    first = first.scatter_reduce(0, segment[is_top], rows[is_top], reduce="amin",
                                 include_self=True)
    return float((best_t - t[first]).sum())


def main() -> int:
    import torch
    from torch import nn

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--corpus", type=Path, required=True)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--shape", required=True, help="e.g. 256,128,64")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--rank-weight", type=float, required=True,
                        help="lambda; 0 = the volume trainer's objective")
    parser.add_argument("--temperature", type=float, default=0.02,
                        help="T, in points of equity")
    parser.add_argument("--rank-groups", type=int, default=512,
                        help="decisions per ranking batch")
    parser.add_argument("--holdout-parts", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261013)
    parser.add_argument("--epoch-rows", type=int, default=4_000_000)
    parser.add_argument("--max-epochs", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=8192)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--schedule", choices=("cosine",), default="cosine")
    parser.add_argument("--select", choices=("bce", "regret"), default="bce",
                        help="hold-out criterion for the kept epoch")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()

    shape = [int(w) for w in args.shape.split(",")]
    torch.manual_seed(args.seed)
    device = torch.device(args.device)

    train_parts, hold_parts = select_parts(args.corpus, args.rows, args.holdout_parts, args.seed)
    table = value_table(train_parts + hold_parts)
    x, y, starts, sizes = load_grouped(train_parts, table, args.rows)
    hx, hy, hstarts, hsizes = load_grouped(hold_parts, table)

    print(f"T72 rang : {x.shape[0]:,} lignes, {starts.size:,} décisions "
          f"(taille moyenne {sizes.mean():.1f}), validation {hx.shape[0]:,} lignes / "
          f"{hstarts.size:,} décisions ; forme {shape} = {macs(shape):,} MACs ; "
          f"λ={args.rank_weight} T={args.temperature}", flush=True)

    gx = torch.from_numpy(x).to(device)
    gy = torch.from_numpy(y).to(device)
    gstarts = torch.from_numpy(starts).to(device)
    gsizes = torch.from_numpy(sizes).to(device)
    ghx = torch.from_numpy(hx).to(device)
    ghy = torch.from_numpy(hy).to(device)
    hrows, hseg = gather_groups(torch, torch.from_numpy(hstarts).to(device),
                                torch.from_numpy(hsizes).to(device),
                                torch.arange(hstarts.size, device=device))
    gtable = torch.from_numpy(table).to(device)

    model = build(nn, shape).to(device)
    opt = torch.optim.Adam(model.parameters(), lr=args.lr)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=args.max_epochs)
    bce = nn.BCEWithLogitsLoss()
    gen = torch.Generator(device=device).manual_seed(args.seed)

    def held_out():
        model.eval()
        n = ghx.shape[0]
        probs = torch.empty_like(ghy)
        total_bce = 0.0
        with torch.no_grad():
            for s in range(0, n, 65536):
                logits = model(gtable[ghx[s:s + 65536].long()])
                total_bce += float(bce(logits, ghy[s:s + 65536])) * logits.shape[0]
                probs[s:s + 65536] = torch.sigmoid(logits)
            gap = float((probs - ghy).abs().mean())
            lost = regret(torch, probs[hrows], ghy[hrows], hseg, hstarts.size)
        model.train()
        return total_bce / n, gap, lost / hstarts.size

    best, best_state, best_epoch = float("inf"), None, 0
    history = []
    start = time.perf_counter()
    steps = max(1, args.epoch_rows // args.batch_size)
    for epoch in range(1, args.max_epochs + 1):
        for _ in range(steps):
            idx = torch.randint(0, gx.shape[0], (args.batch_size,), device=device, generator=gen)
            opt.zero_grad(set_to_none=True)
            loss = bce(model(gtable[gx[idx].long()]), gy[idx])
            if args.rank_weight > 0:
                chosen = torch.randint(0, gstarts.numel(), (args.rank_groups,),
                                       device=device, generator=gen)
                rows, seg = gather_groups(torch, gstarts, gsizes, chosen)
                student = torch.sigmoid(model(gtable[gx[rows].long()]))
                loss = loss + args.rank_weight * rank_loss(
                    torch, student, gy[rows], seg, args.rank_groups, args.temperature)
            loss.backward()
            opt.step()
        held, gap, lost = held_out()
        sched.step()
        history.append((epoch, held, gap, lost))
        criterion = held if args.select == "bce" else lost
        if criterion < best - 1e-9:
            best, best_epoch = criterion, epoch
            best_state = {k: t.detach().cpu().clone() for k, t in model.state_dict().items()}
        if epoch % 10 == 0 or epoch == 1:
            print(f"  époque {epoch:4d}  bce {held:.6f}  |écart| {gap:.5f}  "
                  f"regret0 {lost:.5f}  lr {opt.param_groups[0]['lr']:.1e}  "
                  f"{time.perf_counter() - start:.0f} s", flush=True)
    model.load_state_dict(best_state)
    model = model.cpu().eval()
    export(model, shape, args.out)
    opening = read_back(args.out, shape)

    kept = [h for h in history if h[0] == best_epoch][0]
    summary = {
        "date": date.today().isoformat(), "tool": "tools/distill_rank_t72.py",
        "teacher_labels": "0-ply, cubeless_prob5_768_768_256_256_256 (build_distill_corpus)",
        "rows": int(x.shape[0]), "decisions": int(starts.size),
        "train_parts": [p.name for p in train_parts],
        "holdout_parts": [p.name for p in hold_parts], "holdout_rows": int(hx.shape[0]),
        "holdout_decisions": int(hstarts.size),
        "shape": shape, "macs": macs(shape), "seed": args.seed,
        "rank_weight": args.rank_weight, "temperature": args.temperature,
        "rank_groups": args.rank_groups, "select": args.select,
        "epoch_rows": args.epoch_rows, "batch_size": args.batch_size, "lr": args.lr,
        "schedule": args.schedule, "max_epochs": args.max_epochs,
        "best_epoch": best_epoch, "epochs_run": history[-1][0],
        "holdout_bce": kept[1], "holdout_mean_abs": kept[2], "holdout_regret0": kept[3],
        "history": [list(h) for h in history],
        "seconds": time.perf_counter() - start, "sha256": sha256(args.out),
        "opening_position": opening, "verdict": "AUCUN — la force se lit sur T70",
    }
    args.out.with_suffix(".summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    print(f"  époque gardée {best_epoch}, bce {kept[1]:.6f}, |écart| {kept[2]:.5f}, "
          f"regret0 {kept[3]:.5f} → {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
