# Data-quality approaches

Five decisions in `clean.py` and `quality.py` have more than one reasonable answer. Each one is a
key in the `dq:` section of `config/thresholds.yaml`. Pick an approach per decision, in the
config or for one run:

```bash
uv run run.py --input input/mvp1 --output output \
    --set dq.clock_offset=exclude --set dq.fallback=rescale
```

The first value of each key is the default. The choice is part of the config hash, so it is
saved in `summary.json` and printed on report page 6. An unknown value is refused at start-up.
The decisions are independent, so any combination runs. Each option was checked alone against its
source branch (see Evidence).

| Key | Values | What differs |
| --- | --- | --- |
| `dq.clock_offset` | `shift` (1A) | Move the records of a hub whose clock ran a whole number of hours off to the true time. Keeps the data, but the new time is an estimate |
| | `exclude` (1B) | Keep the label, flag every measure `clock_offset`, never count them as conflicts. Nothing is placed at a guessed time, but the hub loses those days |
| `dq.drift` | `change_point` (2A) | Hub / row ratio against the hub's own normal ratio (5 % tolerance). The start is moved back to where the ratio began to move |
| | `contract` (2B) | Raw hub / row ratio outside +-10 % on a 7-day median. The start is the day the rule fires. The first draft of the contract, kept as a reference |
| `dq.fallback` | `row_median` (2A) | Replace a drifting irradiance sensor with the median of the trusted hubs in its row |
| | `rescale` (2C) | A drifting sensor's own value divided by that day's drift factor (source `hub_corrected`). Keeps the hub's own cloud detail. Stuck sensors still use the row median |
| `dq.humidity` | `peers` (3A) | Daily median humidity far (20 points) from the row median for 3 days |
| | `self_check` (3B) | The hub alone: at least half of a day's readings within 1 point of 100 % for 3 days. Works in a row with one hub, but a long real fog would also match |
| `dq.sentinel` | `listed` (4A) | `validation.sentinel_measures` says which measures a sentinel applies to (327.6 only on `temp_c`). Needs a list that matches the site |
| | `context` (4B) | A sentinel value is a sentinel outside the valid range, or inside it when it is far from its neighbours at that time. No list to keep in sync |

Thresholds for each approach sit next to it in `validation`, `clean` and `quality`.

## Evidence

`scripts/dq_compare.py` ran the base and the five alternatives on the real data and on a copy with
planted faults (`scripts/inject_faults.py`, our own synthetic truth, no answer key). All of them
found 6 of 6 planted faults with 0 false alarms. They differ here:

| Case | Result |
| --- | --- |
| `exclude` | H02 usable 95.29 % against 99.09 %: the 14 offset days are lost. Everything else equal |
| `contract` | H09 drift found from 2026-04-08, 79 days after `change_point` (2026-01-19). Mean start error 18.5 days against 0.83. The slow-drift fault was 109 days late |
| `rescale` | Irradiance value error 0.12 % and 0.11 % on the planted drifts, against 1.02 % and 1.08 % |
| `self_check` | H09 humidity from 2026-01-29 against 2026-01-26. Mean start error 1.0 day against 0.83 |
| `context` | Flags the 327.6 reading at night (10 of 10 against 0 of 10). Keeps 23 of the 24 real irradiance readings of 327.6 |

Each option, selected here, gives the same output as the branch it came from (`cleaned` and
`quality`, every frame, on both datasets). Defaults give the same output as the SOL-20 and SOL-21
base. Combinations are not compared with a source branch. `test_dq_options.py` runs all five
together on the fixture.

## Which to use

The defaults are the base. On this evidence `rescale` and `context` are better than their
defaults and cost nothing on the real data. `exclude` is the cautious choice if shifting records
by an estimated offset is not acceptable. `contract` is only a reference. Changing a default is a
one-line config change, so it can wait until the team agrees.
