# Strawberry Harvest Bench

A simulation-first bench for an autonomous strawberry-harvesting robot: generate
a gutter of plants, let a policy work it, and score what happened against the
simulator's own ground truth.

The point is not the picking algorithm. It is the harness around it — the thing
that lets a field failure be recreated offline and a fix be proved before any
code reaches a real machine. See [DESIGN.md](DESIGN.md) for why that is the
asset, and for the full build order.

```
scenario (seeded)  ──▶  MJCF scene  ──▶  MuJoCo cell  ──▶  telemetry
       │                                      ▲                 │
       │                                 policy picks           ▼
       └──────────── ground truth ──────────────────────▶  metrics vector
```

## Quick start

Needs Python 3.12 and `uv`.

```bash
uv sync
uv run pytest
uv run harvest run --scenarios 20 --seed 1 --out runs/baseline
```

`harvest scene --seed 3` prints the generated MJCF for one scenario, which is
what to look at when the physics does something surprising.

## How it works

- **`scenario.py`** — a seeded gutter of berries: position, radius, ripeness,
  peduncle direction, occlusion. This is the ground truth, and the policy never
  sees it.
- **`scene.py`** — turns a scenario into MJCF. Each berry is a free body held by
  a weld to a static anchor standing in for its peduncle; cutting the stem means
  deactivating that constraint. Occluded berries get a real leaf in front of
  them, placed from the berry's own random stream, so the arm can collide with
  it.
- **`cell.py`** — the `HarvestCell` interface and its MuJoCo backend. `observe()`
  returns a noisy view; `pick()` drives the arm, cuts, carries the berry to the
  punnet and drops it into a cup, and reports what the physics did.
- **`ik.py`** — damped least squares, position only, over four joints. The wrist
  is a dependent joint that keeps the catch tray level.
- **`policy.py`** — the baseline. Deliberately rough; see below.
- **`metrics.py`** — scores a run as a vector, not a single number.
- **`session.py`** — the loop, shaped after `../lab-robot`'s `run_campaign`:
  config dataclass, injectable logger, optional observer, `out_dir=None` to keep
  a run in memory.
- **`photocase.py`** — the demo's field failure: a photo measured by colour and
  turned into a scene, worked by whatever code is importable, and filmed.
- **`demobake.py`** — builds the static demo page: runs the code, films the
  simulation, runs Claude Code on a scratch copy, and writes `web/demo/data.js`.
- **`camera.py`** — colour, depth and segmentation from the cell's cameras.
  Debug annotations are hidden for every render: the cut points are drawn as
  sites, and a detector that could see them would be reading the answer off the
  picture.
- **`imaging.py`** — a PNG writer. A dependency on Pillow to write a dozen
  images is not worth it when the uncompressed-RGB case is this small.

## What the camera sees

Two cameras. A fixed **survey camera** facing the gutter, which is what
perception plans from, and a **wrist camera** for the close-up.

The scene is built to make that a real problem rather than an easy one:

- Berries are textured by ripeness, from pale green to deep red, with speckle
  marks standing in for achenes. Colour has to carry ripeness, because that is
  what a detector reads it from.
- A cluttered green canopy sits behind the fruit. Without it the camera sees red
  on black and any method scores near perfect, which would make comparing two
  detectors pointless.
- Leaves sit at varied angles. Some are squarely in front of a berry, some miss.

Segmentation supplies the labels for free — the simulator already knows which
geom every pixel belongs to — so there is nothing to annotate and no dataset to
license.

Rendering is headless through EGL, on the GPU (see below). All of the decoration (the tapered tip, the
sepals, the stem, the canopy, the clutter) is `contype=0 conaffinity=0`: it
changes what the camera sees and nothing about the physics. The baseline is
byte-identical before and after it was added, which is the point.

Outcomes come from the physics rather than a lookup table. A berry is caught
because it landed in the tray. A stem tears because the cutter pressed on fruit
that was still attached. A neighbour is knocked because the arm struck it.

## Reading the camera

`--detector colour` swaps ground truth for pixels. A hand-tuned threshold picks
out what is saturated and not leaf-green, connected components give candidate
blobs, and depth plus the camera intrinsics turn each one into a world position.

Two details that cost a measurement each:

- **Depth lands on the near surface, not the centre.** Uncorrected that is a
  systematic 15 mm bias toward the camera, and the arm drives straight into it.
  The detector pushes along the viewing ray by the estimated radius.
- **Hue predicts ripeness almost perfectly under fixed light.** 70 berries put
  it at `ripeness = -0.0156 × hue + 0.894`, MAE 0.013 — which made ripeness a
  non-problem. Lighting now varies per scenario in brightness *and tint*;
  brightness alone changes nothing, because hue is invariant to it.

The detector does not know which berry is which, and neither does the robot.
A detection is a position with a made-up label, and what gets cut is whatever
peduncle is within 30 mm of the blades. Matching detections back to real berries
happens only in scoring.

## Where it stands

Steps 1 to 3 of 7 in DESIGN.md are done: the cell runs, the baseline works it,
every attempt is scored and logged, and perception can read a rendered camera
instead of the simulator's ground truth. Every caught berry is carried to a
punnet and packed, and success counts what reaches it. 90 tests pass.

Rendering is required — the metric buckets measure occlusion from pixels — and
`MUJOCO_GL` defaults to EGL so it works without a display.

Physics always runs on the CPU; the cameras render on the GPU. The suite
starts its workers with `spawn`, never `fork`: a parent that has rendered holds
an OpenGL context, and a forked child inherits its driver state without the
threads behind it and hangs. That is the likely cause of what once looked like
the GPU freezing the machine: since the switch to `spawn`, the full tier runs
on the GPU in about 10 s on 24 cores without trouble.

`HARVEST_RENDER=cpu` renders with Mesa's software rasterizer (llvmpipe)
instead, by hiding the NVIDIA EGL vendor, for a machine with no usable GPU. It
is about half again slower, and its pixels are not identical: over the full
tier it changes one decision (S0015). A baseline only gates exactly against
runs on the renderer it was recorded with. Any of the variables set in
`harvestbench/__init__.py`, if already in the environment, wins over the
default.

Over 20 scenarios (`--seed 1`), 91 ripe berries, both perception paths:

| | sensor model | camera + colour threshold |
|---|---|---|
| success (ripe packed) | 58.2% | 61.5% |
| ripe packed | 53 / 91 | 56 / 91 |
| ripe caught | 60 / 91 | 60 / 91 |
| ripe never detected | 1 | 2 |
| false picks | 0 | 0 |
| torn stems | 5 | 5 |
| knocks | 1 | 2 |
| caught, then: right cup / wrong cup / spilled | 51 / 7 / 7 | 59 / 3 / 4 |
| bruised on landing | 21 | 29 |
| unreachable | 27 | 28 |
| attempts | 97 | 99 |

Success by measured occlusion, camera path: **clear 75% (53/71) · partial 29%
(2/7) · heavy 8% (1/13)**. That is where the work is.

The two paths catch exactly the same ripe berries. Where they part is after
the catch: a berry lands in the tray a little differently, rides and drops a
little differently, and over a handful of scenarios that is a few berries
either way. Both paths estimate a berry's size equally well (bias under 1 mm,
spread 2.5 mm over 230 berries), so it is not the aim.

### The sensor model is fitted, not assumed

The first time both paths ran, the camera scored 51.7% against the sensor
model's 29.7%. Reading pixels beat being told the answer, which is not a thing
that should happen.

The cause was the sensor model, not the camera. It dropped a berry with
probability `0.85 x occlusion`, using the scenario's **nominal** occlusion — and
rendering had already shown that number mostly corresponds to nothing. It was
discarding 19 of 91 ripe berries for no physical reason while being too
generous about where the rest of them were.

So it was refitted against 150 berries read by the real detector, bucketed by
occlusion measured from pixels:

| occlusion | detected | position error | ripeness error |
|---|---|---|---|
| none | 100% | 6.4 mm | 0.015 |
| light | 100% | 6.0 mm | 0.009 |
| partial | 100% | 11.3 mm | 0.013 |
| heavy | 89% | 18.1 mm | 0.018 |

Detection does not decay gradually — it holds until a berry is about 60% hidden
and only then starts to fail — so the dropout model became a threshold rather
than a line. The gap between the two paths went from 22 points to about one.

That is what the cheap path is for: the same answers without rendering, usable
for a large suite. It is a stand-in for the camera, and it is only worth
anything for as long as it keeps tracking it.

### Occlusion is measured, not declared

The metric buckets read pixels now. Rendering each scenario twice, once with
the leaves and once without and with the arm left out of both, gives the real
figure. It is a different distribution from the one the scenario declares:

| | clear | partial | heavy |
|---|---|---|---|
| nominal | 41 | 39 | 11 |
| measured | 71 | 7 | 13 |

A leaf either lands over a berry or misses it. Very little is half-covered, and
the nominal value was inventing a middle that is not there.

## Packing what it picks

A harvested berry is not a berry in a tray under the cutter. The real machine
puts each one in its own cup in a punnet, and handling is where a premium berry
gets bruised, so the bench does that too: the arm backs out, carries the berry
to a punnet at the home end of the rail, and drops it into the next cup.

The punnet sits outside the survey camera's view. A test holds it there,
because adding a tray to the cell must not change what perception reads.

### What building it turned up

Packing could not work until three things that had been wrong all along were
fixed, and the first two had been distorting the headline numbers:

- **The catch was scored before the retract, and the retract threw the fruit
  away.** `park()` handed all five joints a far-off target at once. The wrist
  servo got there in a fraction of a second and the heavy joints took seconds,
  so the tray spent the move tipped, and the move itself was a lunge. **113 of
  117 caught berries went over the side** on the way back, after being counted
  as picked. With fruit aboard the arm now follows a minimum-jerk trajectory,
  with the wrist slaved to keep the tray level the whole way.
- **The home pose drove the arm into the gutter.** `HOME_Q` folded the arm so
  the tray sat under the gutter's footprint at the height of its underside. At
  rail 0 that is just past the gutter's end, so the pose itself looked fine,
  but the arm took that shape long before the carriage got back, and dragged
  the tray along the gutter's underside on the way. **127 of 203 parks never
  arrived**, the arm was on the gutter for 370 s of simulated time over the full
  tier, and every next approach started from wherever it had jammed. A berry
  riding along was scraped off. Home is now folded back, clear of the gutter
  and the fruit wherever the carriage is: 198 of 203 parks arrive, and contact
  with the gutter is left only where the head-on approach reaches fruit hanging
  right under it.
- **A simulated berry rolled like a ball bearing.** MuJoCo's default contact has
  no rolling resistance, so an ellipsoid rolled off the open side of the tray
  under the gentlest braking. The tray now has rolling friction. Putting it on
  the berry instead raised the force on an attached berry by half again and
  turned near misses into torn stems; on the tray, the cutter's contacts with
  attached fruit stay exactly as the thresholds were set.

The home pose was most of the damage. Over the full tier, fixing it alone took
torn stems from 30 to 12 and knocks from 31 to 2, and packed success from 55.1%
to 61.7%: an approach that starts from a jammed arm swings through the fruit on
its way in. Unreachable rose from 49 to 55 — probably berries that the old
swing happened to reach and the head-on path cannot, though that has not been
checked attempt by attempt.

The wrist range also had to grow from ±1.6 to ±3.2 rad: with the arm reaching
down to the punnet, the tray could not even be held flat.

### How it drops a berry

Over the cup the tray's floor opens and the berry falls straight down. Tipping
it out over the edge was tried first and could not be made accurate: the berry
slid five centimetres across the tray, left at about 0.35 m/s, and hopped the
cup walls. With nothing pushing it sideways, where it lands depends on where it
sat, and in the carries traced the berry ended up against the tray lip — so the
arm aims that spot, worked out from its own estimate of the berry's radius.

The punnet's two columns are 11 cm apart and packing starts at the far row, so
the tray never comes down over a cup that is already full. The spacing came
from the data — with the columns side by side, the second cup in every row
missed far more often — and the order from the geometry: over a cup, the tray
hangs out toward the rail by most of its length.

### The lever

A bruise is judged by landing speed, and landing speed is set by the release
height. Over the full tier, 130 berries packed:

| release height | bruised | wrong cup |
|---|---|---|
| 4.5 cm (baseline) | 57 | 9 |
| 2.8 cm | 0 | 10 |

The baseline releases high, which is safe for the tray and rough on the fruit.
Moving that number is the kind of change `harvest gate` exists to judge: here
it takes the bruises away for one more berry in the wrong cup.


## From a field log to a fix

The bench knows a berry was unripe, or that a stem tore. A machine in a
polytunnel knows none of that. It has what its own sensors recorded, and the
first job is working out which of those recordings mean something went wrong.

```bash
uv run harvest run --scenarios 4 --seed 1 --detector colour --out runs/field
uv run harvest incidents runs/field
```

```
S0003/d03
  [high] stem_tear: cutter drew 7.5 N before cutting: it was on fruit, not on the stem

S0004/d02
  [watch] bruise_risk: cutter pressed 3.8 N on attached fruit
  [high] dropped: the cut fired but the tray never registered fruit

2 of 20 attempts flagged
```

`incidents.py` reads only what a real machine has: motor current on the cutter,
whether the tray registered a load, perception's own estimate, commanded pose
against achieved pose. It never touches the simulator's truth. That is reserved
for `validate()`, which scores the flags over scenarios where the answer is
known — calibrate in the lab, run on the farm.

### What that measured

| flag | flagged | real | precision | recall |
|---|---|---|---|---|
| stem_tear | 23 | 23 | 100% | 100% |
| dropped | 2 | 2 | 100% | 100% |
| unripe_risk | 1 | 0 | — | — |

Two warnings about the top two rows. **They are perfect by construction**: the
simulator decides a stem tore using the same force threshold the flag uses, and
"the tray registered fruit" is how it decides a berry was caught. Both are
measuring the model twice. A real cutter's current is noisier and is not
attributed to one berry, so the field numbers would be worse — how much worse
is unmeasured.

The third row is the honest one, and the investigation behind it is the point.

### The investigation

The first version flagged unripe picks by margin alone: if the estimate landed
near the threshold, suspect it. Over 30 scenarios that scored **13% precision
and 43% recall** — an operator chasing those flags would waste most of a day.

So a second look was added. After the cut the fruit is in the tray, a hand's
width from the wrist camera, lit and unoccluded, and reading ripeness there is
accurate to about 0.02. Harvesters carry an outfeed camera for exactly this.

That still flagged nothing. Printing the seven supposed bad picks explained why:

```
pick             truth   survey  tray
S0011/d05        0.60    0.61    0.61
S0012/d00        0.97    0.94    0.95     <- not unripe. overripe.
S0016/d04        0.59    0.60    0.62
S0017/d03        0.96    0.93    0.94     <- overripe
S0018/d03        0.96    0.93    0.94     <- overripe
S0018/d04        0.97    0.94    0.95     <- overripe
S0024/d02        0.59    0.60    0.61
```

Four of the seven were not unripe at all. They were past it — `should_pick` is
a window, `0.60 <= ripeness < 0.95`, and the flag only ever watched the bottom
of it. The other three sit within 0.01 of the line, where no sensor can help
and the two berries either side are the same berry.

Both of those were fixed: the flag now checks both bounds, and `metrics.py`
counts fruit within 0.03 of either bound as `borderline_picks` rather than
`false_picks`. After which the headline changes — **false picks over 30
scenarios: 6 becomes 0, with 7 borderline.** The robot was never picking
clearly wrong fruit. The metric was.

A third fix came out of running the report: the margin flag fired even when the
tray camera had already confirmed the fruit was fine, which was most of the
noise. Suppressing those took the report from 6 flags on 20 attempts, 4 of them
bogus, to 2 flags that are both real.

### What it leaves

Torn stems were the failure worth working on — 23 over 30 scenarios when this
was written, 12 over the 40-scenario full tier since the home pose was fixed —
and the bench already localizes them: the cutter aims 12 mm above the
estimated top of a berry, position error runs 6 mm clear and 18 mm when a leaf
is in the way, and the two overlap. That is the next change, and `harvest gate`
is what will say whether it helped.

## The demo page

**Live at https://harvest.isaacon.dev** (Cloudflare Pages).

```bash
uv run harvest demo-bake --agent              # run everything, the AI agent included
python3 -m http.server 8848 --directory web   # then open http://127.0.0.1:8848/
```

To publish a new bake, upload `web/` again. The Pages project uses direct
upload rather than the GitHub integration, so a push alone does not redeploy:

```bash
CLOUDFLARE_API_TOKEN=... uv run --no-project --with blake3 python scripts/deploy_pages.py
```

A recorded demo of real operations: one field failure, from report to pull
request, on one static page. Every
number, video and line of code on it was produced by `demo-bake` running the
real code; the page only reads `web/demo/data.js`. Without `--agent` it bakes
again from the agent's last copy.

1. **Field logs.** Nine ordinary picks and one that is not, selected: FIELD-0417,
   a `stem_tear`, with its log lines and the photo attached to the incident
   (`web/demo/field-photo.png`) — a ripe berry with an unripe one hanging in
   front, over its top, where the stem is cut.
2. **The photo as a simulation** (`photocase.py`). Colour finds the ripe and the
   unripe fruit and measures each in pixels. A photo has neither scale nor
   depth, so two numbers are assumed and stated: the ripe berry is 20 mm in
   radius, and the unripe one that overlaps it hangs 70 mm in front.
3. **Reproduce.** The original code works the cluster like any gutter, goes for
   the ripe berry head-on and drives into the unripe one: the field log's
   failure, filmed by MuJoCo's renderer and encoded with ffmpeg.
4. **The fix.** Claude Code, run headless on a scratch copy of the code
   (`runs/demo/work`), with the field report and one command, `./check.sh`: the
   cluster, the demo tier and the regular smoke tier. It may not edit the
   experiment, the gate or the world, nor read the simulator's ground truth.
   The page shows its explanation, the diff, and the cluster filmed again on
   its code.
5. **Smoke test.** Which tiers and scenarios ran on the fixed code, and that
   they passed.
6. **Pull request.** The agent's title and description, the checks, and the
   review request. Nothing is pushed anywhere.

What getting there turned up:

- **Two berries touching came out as one.** The detector merged the ripe berry
  with the unripe one over it, read the pair as unripe, and never attempted
  the pick. A blob that holds two distinct colour populations is now split.
  Splitting every blob by colour moved the detections in 36 of 40 full-tier
  scenarios; splitting only the two-population ones moves none.
- **`python -m harvestbench.cli` did nothing.** There was no `__main__` guard,
  so it exited 0 without running — and the demo's smoke check passed without
  having run. Caught in the first rehearsal, after the agent had finished.
- **Not every leaf-blocked or fruit-blocked case can be fixed.** With the
  unripe berry 50 mm in front, no approach clears it; at 70 mm an angled one
  does. The depth is an assumption either way, and the page says so.

Two earlier rehearsals, both with Opus 5.5, both fixing the case:

| | first | second |
|---|---|---|
| time, turns | 7 min 23 s, 69 | 7 min 36 s, 63 |
| the fix | angled approach chosen from the other detections; straight-line retract | angled approach; corrected top estimate for a covered berry; retract lifted 2 cm |
| demo tier (catch only) | pass | pass |
| smoke and full tiers | pass, no scenario changed | **fail**: spills 6 → 15, catch rate 64.8% → 63.3% |

The agent's `./check.sh` then ran only the demo tier, which judges picking up to
the catch, so the second fix's extra spills were invisible to it. An agent
writes a different fix each time; what it is held to has to be the whole
standard, not the part the demo is about. `./check.sh` now runs the regular
smoke tier too, and the page shows the run made under that rule.

## The regression gate

```bash
uv run harvest gate --tier smoke          # every commit
uv run harvest gate --tier full           # every pull request
uv run harvest gate --tier demo           # picking only, two chosen scenarios
uv run harvest gate --tier smoke --update # record a new baseline
```

The runs are deterministic, so the diff against `baselines/<tier>-<path>.json`
is exact: if a number moved, the code moved it.

| tier | scenarios | blocks on | time |
|---|---|---|---|
| smoke | first 6 seeds | packed success down, damage up, false picks up | ~10 s |
| full | first 40 seeds | the same | ~10 s on 24 cores |
| demo | S0010, S0025 | catch rate down, torn stems or knocks up, false picks up | ~10 s |

The demo tier judges picking only — up to the catch. The carry and the drop
still run, so each scenario plays out as it would, but spills and bruises are
recorded rather than judged. Its two scenarios are the ones where every ripe
berry is caught with nothing torn or knocked, on both perception paths, so a
change that breaks picking shows at once and a pass is unambiguous.

Every tier also checks that the cheap sensor model still tracks the camera, on
catch rate rather than packed success: the two paths catch exactly the same
ripe berries in every tier, while what happens afterwards on the way to the
punnet differs by a berry or two either way, and that is not the sensor
model's doing.

## What is deliberately rough

The job this is built for is not greenfield — it asks for ramping up on an
existing codebase and owning an area of it. So the baseline is written to run
and to be visibly improvable:

- A hardcoded ripeness threshold on a noisy estimate, with no allowance for
  uncertainty. Produces the false picks and some of the skipped ripe fruit.
- Confidence and occlusion are read and ignored, so full cycles are spent
  reaching for berries behind leaves.
- One attempt per berry, no retry from another angle.
- Head-on approach, ignoring which way the peduncle runs.
- Left to right along the gutter, with no account of rail travel.
- Berries are released from 4.5 cm above the cup floor, high enough to bruise
  about half of them.

Each is a metric waiting to move. Steps 5 and 6 are where that happens.

## Assumptions that are guesses

Worth saying plainly, because the numbers above depend on them:

- **The damage thresholds are not calibrated.** 6 N on an attached berry counts
  as a torn stem and 1.5 N on a neighbour counts as a knock. Both are plausible
  for fruit — a strawberry detaches at a few newtons — but neither comes from a
  measurement. Changing them moves the headline success rate, since a pick that
  presses too hard is counted as damage instead of a success.
- **The bruise threshold is a guess too.** Landing faster than 0.77 m/s, a free
  fall from 3 cm, counts as bruised. Strawberries do bruise easily, but the
  number is not from a lab, and it decides the bruise count outright.
- **The end effector drops fruit; the real one grips it.** Oishii's arms place
  each berry with a gripper. This one keeps its catch tray and opens it like a
  trapdoor, because the cut, the catch and every force threshold were
  calibrated against the tray and a gripper would start all of that over.
- **Force replaced displacement for a reason.** Displacement was the first
  attempt and it was wrong: the weld has to be stiff enough that gravity does
  not sag a berry, and at that stiffness a berry pushed by the arm moves under
  half a millimetre. Berries read as walls, and damage never fired at all.
- **The scenario's `occlusion` field is now only a scene parameter.** It decides
  whether a leaf is generated and how wide, and nothing else reads it. Metrics
  and the sensor model both use the measured figure. The field keeps its old
  name, which is misleading, and it should be renamed.
- **The ripeness fit is lighting-specific.** `-0.0156 x hue + 0.894` was fitted
  under the reference lighting and then the lighting was made to vary, which is
  the intended weakness of a fixed threshold. It has not been refitted, and the
  false-pick count is where it shows.
- **The survey camera wastes about half its frame.** It is 4:3 looking at a
  wide, shallow row, so the picture is letterboxed and the fruit gets fewer
  pixels than it could. A wider sensor would fix it, and would also change the
  detector's numbers and invalidate the fit above, so it has not been touched.
- **The sensor model is fitted to one detector on 150 berries.** Change the
  detector, the lighting or the plant layout and it stops being a stand-in for
  anything. The gate checks that it still tracks the camera's catch rate — the
  part of the job perception decides — not the packed success rate, which also
  carries the carry and the drop.
- **The sim-to-real gap is unmeasured**, and nothing here claims otherwise. The
  bench is only worth as much as that gap, which is why DESIGN.md makes tracking
  it part of the design rather than an afterthought.
- **Berry spacing hides the damage metric.** The generator spaces berries about
  19 cm apart, and at that spacing the end effector threads between them: the
  cutter head rides above a neighbour while the tray passes below. Clustered
  scenarios (step 6) are what make knocks common. A unit test forces the
  detection to fire so the metric is at least provably live.

## Not built yet

Recreation against recorded runs, a scenario corpus mined from failures, and
the agentic loop. The regression gate exists; see above. Build order and what each step is for are
in DESIGN.md.
