# Strength: the T35 campaign

## Protocol

**Full configuration** — network, 2-ply filtered search `(0,1,3)`, match equity, exact bearoff
tables, 2-ply cube — against **GNU Backgammon at the same setting**: 2-ply, filter `(0,1,3)`, 2-ply
cube, `prune = 1` (its real play).

Common dice, duplicate pairs, seed 20260810, bootstrap over pairs.

## Result

| Half | Volume | Measure | 95 % CI |
|---|---|---|---|
| **money**, cubeful | 50 000 pairs | **−0.0119 ppg** | [−0.0310 ; +0.0074] |
| **match**, 7 points | 50 000 pairs | **50.42 % MWC** | [50.16 ; 50.69] |

## The verdict, in exact terms

- **Equivalent: confirmed.**
- **Stronger: not established.** The +0.0400 ppg measured *cubeless* does not reproduce once the
  cube is wired in.
- **eXtreme Gammon: not measured.**

## A campaign that was thrown away

**The first match half was invalid and discarded.** It gave 56.4 % MWC against parity — all the
edge concentrated where the cube lives, peaking at 60.3 % post-Crawford.

The cause: a verdict classifier read *"Never redouble, take (dead cube)"* as a double. The campaign
therefore made GNU Backgammon **redouble exactly where it says never to**.

```{admonition} The signature was in the journal, unlooked for
:class: note

**84.1 % of post-Crawford pairs reached a cube of 4 or 8**, where correct play caps at 2. After the
fix: **2.2 %**, and cube-8 disappears entirely.
```

The invalid journal is **kept** as evidence, and marked: no figure comes out of it.
