# In-Theaters Projection Uncertainty — Floor + Tight Range

**Status:** Approved 2026-06-28

## Context

The forecast pipeline produces physically impossible 80% ranges for films that
are deep into their theatrical run. The canonical example is *The Devil Wears
Prada 2*, which has already banked **$219,602,888** in the wager window, yet its
displayed 80% range reads **[$194.4M, $251.2M]**:

- The **p10 floor ($194.4M) is below money the film has already earned** — a
  movie cannot finish the window having grossed less than it already has.
- The **p90 ceiling ($251.2M) is far above what the film can realistically
  reach** — its weekly deltas are decaying fast (+$5.6M → +$2.9M → +$1.45M over
  the last three weeks), leaving only ~$1–2M to earn.

Both errors come from a single modeling flaw, so both are fixed by a single
change. This is a model-correctness fix; it changes no game rules, no scoring,
and no data.

## Root cause

`sigma` (the lognormal spread) is applied to the **entire in-window total**.
Every draw — both the Monte Carlo sample in `simulate.py` and the displayed
p10/p90 in `build.py` — uses the form:

```
total = median * exp(sigma · z)
```

This treats *all* of a film's projected total as uncertain, including the large
portion already banked at the box office. For a film like DWP2 where ~99% of the
total is already locked in, spreading variance across the whole total pushes the
low tail below the banked amount and the high tail far past what little gross
remains.

## The fix: put uncertainty on the *remaining* gross only

The certain, already-banked gross (`floor`) should not vary. Only the
**remaining** (unbanked) gross carries uncertainty. The new draw form, used
everywhere a sample or percentile is computed, is:

```
total = floor + (median − floor) * exp(sigma · z)
```

where `floor` = the film's current banked in-window gross (`0` for pre-release
titles, which have banked nothing).

Properties:

- **Median preserved.** At `z = 0`, `total = floor + (median − floor) = median`.
- **Floor is automatic.** `exp(sigma · z)` is always positive, so a sample can
  never fall below `floor`. No clamp, no `np.maximum`, no point-mass artifact.
- **Ceiling self-tightens.** `median − floor` is the only quantity that scales
  with sigma. For old films it is tiny (~$1.4M for DWP2), so the band collapses
  to a few hundred thousand dollars on either side. For young films it is large,
  so the band stays honestly wide.
- **Pre-release is unchanged.** With `floor = 0`, the form reduces to
  `median * exp(sigma · z)` — identical to today's behavior.

For DWP2 this yields a band of roughly **[$220.8M, $221.2M]** instead of
[$194.4M, $251.2M].

### Why no per-week sigma tuning

An earlier idea was to additionally shrink `sigma` for films 4+ weeks into their
run. The remaining-based model already produces exactly that effect — old films
have almost nothing left to earn, so their range collapses on its own — without
introducing a hand-tuned week threshold. We deliberately keep the existing
`_sigma_from_weeks` curve unchanged. This keeps the model honest: a younger film
with genuinely uncertain remaining gross still gets a wide band, rather than
being artificially narrowed by a magic constant.

## Architecture

Three source files change; `decay.py` and `preopening.py` are untouched.

```
summer_movie_wager/types.py            — add `floor` field to Projection
summer_movie_wager/render/build.py     — populate floor; remaining-based p10/p90
summer_movie_wager/model/simulate.py   — remaining-based Monte Carlo sampling
```

### Data flow

`Projection` gains a single field:

```python
floor: float = 0.0  # current banked in-window gross; uncertainty applies above this
```

The default of `0.0` means every existing `Projection(...)` construction (in
tests and elsewhere) remains valid, and any consumer that does not set `floor`
gets today's behavior.

`build.py:_project_all` sets the floor from the same cumulative gross it already
has in hand — the value comes straight from the normalized movie record, so no
new plumbing through the decay model is required:

```python
floor = m["cumulative"] if m["status"] == MovieStatus.IN_THEATERS else 0.0
```

`build.py:_build_movie_rows` and `simulate.py` both swap their draw formula to
the remaining-based form. Because both read `floor` and `median` off the same
`Projection`, the displayed band and the simulated outcomes stay consistent.

### Edge cases

- **Zero-median films** (pre-release with no analyst entry): `floor = 0`,
  `remaining = 0`, every sample is `0` — unchanged.
- **In-theaters films past `WINDOW_END`**: `project_decay` returns
  `median == cumulative`, so `remaining = 0` and every sample collapses to
  exactly `floor` — correct, the total is locked.
- **Defensive clamp**: `remaining` is computed as `max(0, median − floor)` so a
  pathological `median < floor` can never produce a negative remaining (the
  decay model guarantees `median ≥ cumulative`, but the clamp costs nothing).

## Testing

- **`tests/test_simulate.py`** — add a case with an in-theaters-style projection
  (`floor` near `median`, nonzero sigma) asserting that **no sampled total and
  no reported percentile falls below `floor`**, and that the p10–p90 band sits
  within a few percent of `floor`.
- **`tests/test_build.py` / `tests/test_render_snapshot.py`** — p10/p90 values
  for nonzero-sigma rows change under the new formula; refresh expected numbers
  and the rendered snapshot.
- **`tests/test_types.py`** — assert `Projection.floor` defaults to `0.0`.

## Verification

1. `uv run pytest` — all green after the assertion updates above.
2. `uv run python -m summer_movie_wager.render.build --local` — for *The Devil
   Wears Prada 2*, confirm p10 ≥ $219,602,888 and p90 within ~$10M of it
   (≈ [$220.8M, $221.2M]); confirm a young in-theaters film still shows a wide
   band; confirm a pre-release analyst film's band is unchanged vs. `main`.
3. Confirm `forecast_available` and the leaderboard still render — the new
   `floor` field must not break the `Projection` schema or serialization.
