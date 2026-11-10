# Strawberry Harvest Bench

A simulation-first development and regression harness for an autonomous
strawberry-harvesting robot cell.

Target role: Senior Software Engineer, Robotics (Oishii) — perception, motion
planning, controls, and the offline sim / recreation / visualization loop that
tests features before they reach a physical robot.

Built on the skeleton proven by `../lab-robot`, which runs the same shape of
loop for a self-driving lab: a closed loop around a simulated robot, a hidden
oracle, injected failures, recorded telemetry, and a replayable web demo.

## The problem this demo addresses

A harvesting robot fails in ways that are expensive to debug. The berry is
behind a leaf. Two berries grow as a cluster and the gripper takes both. The
cut point on the peduncle is misjudged by 4 mm and the stem tears. Operations
reports "it drops berries on shelf 3 in the afternoon," and that sentence has
to become a code change.

You cannot iterate on this by driving the real robot. Each attempt costs a
berry, the hardware is shared, and the failure is not reproducible on demand.

So the real engineering asset is not the picking algorithm. It is the bench: a
way to **recreate a field failure offline, deterministically, and prove a fix
against it before any code reaches the robot.**

That bench is what this demo builds. The posting asks for exactly this under
"AI Agentic development processes using offline sim, recreation, and
visualization into features that are pre-tested before they land on the
physical robots."

## What carries over from lab-robot

`lab-robot` already solved most of the scaffolding. The domain swaps; the
architecture does not.

| lab-robot | Harvest bench |
|---|---|
| `CampaignConfig` + `run_campaign(cfg, log, observer)` | `RunConfig` + `run_session(...)`, same shape |
| Planner picks 8 compounds per plate | Scenario generator emits a gutter of plants |
| Generated Opentrons protocol | Generated motion plan per berry |
| `opentrons.simulate` runs the real protocol | MuJoCo steps the real physics |
| `Oracle`: hidden AqSolDB logS → noisy A600 | Simulator ground truth → noisy RGB-D frame |
| `FAILURES`: tip pickup, gripper jam | `berry_dropped`, `stem_torn`, `neighbor_knocked`, `gripper_miss` |
| Virtual clock + `telemetry.jsonl` | Same, one record per perceive/plan/execute step |
| Failed plate → rerun same compounds | Failed pick → retry at a new approach angle |
| `Recorder` observer → `web/demo-data.js` | Same observer, same self-contained replay |
| `labrobot compare` → `compare.csv` + `.png` | `harvest suite` → per-scenario metrics diff |
| One Docker container, dataset baked in, offline | Same |
| `.claude/launch.json` serving `web/` | Same |

Decisions worth copying verbatim:

- **Config dataclass with `out_dir: Path | None`.** `None` keeps a run in memory,
  which is what makes a 200-scenario suite cheap.
- **Injectable `log`.** The suite silences per-run logging with `log=lambda *_: None`.
- **Observer hooks instead of a demo-aware core.** The harness does not know the
  web page exists. `Recorder` collects everything for replay.
- **Determinism by construction.** Seed in the config, a separate stream for the
  noise (`seed + 1000`), and a per-item RNG derived from `crc32(id) + seed` so
  the same berry behaves the same way across runs.
- **A real simulator in the loop.** lab-robot's credibility comes from running an
  actual Flex protocol through the official Opentrons simulator, not a toy
  mock. The equivalent here is real physics (MuJoCo) and a real planner, not a
  hand-waved kinematics stub.
- **`window.DEMO_DATA = {...}` in a `.js` file.** The replay page then works from
  `file://` with no server and no build step.

Two deliberate changes:

- **Telemetry stays JSONL first.** My earlier draft reached for MCAP and Foxglove.
  lab-robot shows that plain JSONL plus a vanilla-JS replay page is enough to
  demonstrate the loop, and it costs days less. Add an MCAP writer later as an
  export path, once the loop is worth recording in a standard format.
- **The metrics are a vector, not a scalar.** lab-robot optimizes one number
  (test RMSE). Harvesting has several that trade against each other: pick
  success, damage events, missed-ripe rate, cycle time. The regression gate has
  to reason about a vector, which is the more interesting engineering problem
  and the one the posting describes.

## What the system does

```
                  ┌─────────────────────────────────────────┐
  field logs ────▶│  Scenario corpus                        │
  sim runs   ────▶│  hard cases mined from failures         │
                  └────────────────┬────────────────────────┘
                                   │ deterministic replay
                  ┌────────────────▼────────────────────────┐
   new code  ────▶│  Harness: N scenarios across 24 cores   │
                  └────────────────┬────────────────────────┘
                                   │
         ┌─────────────────────────┼──────────────────────────┐
         ▼                         ▼                          ▼
   metrics + telemetry      web replay of a run        regression gate
   (JSONL → dashboards)     (3D scene + camera)        (block on regression)
```

### 1. Simulated harvest cell

A vertical-farm shelf: gutters of strawberry plants, a 6-DoF arm on a linear
rail, an RGB-D camera on the wrist. MuJoCo for physics and rendering.

Procedurally generated plant state, randomized per scenario:

- berry count, position, size, hang angle
- ripeness, which drives both color and the correct pick/skip decision
- peduncle length and orientation, which sets the cut point
- occluding leaves and berry-on-berry clusters
- lighting, camera exposure, lens blur

This is lab-robot's `Oracle` in a different costume. The simulator knows every
berry's pose, ripeness, and correct cut point exactly; perception only ever
sees a degraded observation of it. Ground truth is free, so there is no
annotation cost and no dataset licensing question.

### 2. Perception

RGB-D frame in, pick targets out.

| Stage | Output | Model |
|---|---|---|
| Instance segmentation | berry masks | YOLO-seg (small) |
| Ripeness | pick / wait / overripe | small CNN head on the crop |
| Pose + cut point | 6D berry pose, peduncle keypoint | keypoint head |
| Reachability | occlusion score, confidence | geometric + learned |

Trained on synthetic frames with domain randomization. Scored on held-out
scenarios, split so that **plant layouts seen in training never appear in
evaluation** — the model has to handle arrangements it has not seen.

Optional: validate against a public real strawberry image set to measure the
sim-to-real gap. Verify the license of any such dataset before using it; do not
assume a Kaggle or Roboflow upload grants reuse.

### 3. Motion planning and controls

- Collision-aware planning into a dense canopy, with approach-angle constraints,
  since the cutter has to come in along the peduncle rather than through a leaf.
- Neighbor-damage avoidance as a planning cost, not an afterthought.
- Retry and give-up policy: how many approach angles before marking a berry
  unreachable. A problem with no defined correct answer, only iterative
  improvement against a metric — which the posting calls out directly.
- A single `HarvestCell` interface with a sim backend and a stub hardware
  backend, so the same control code runs against both. lab-robot's
  `VirtualRobot` is the model for this.

**Python throughout.** The posting accepts any of Python, Rust, or C++, and for
this demo Python is the right answer rather than a concession:

- The demo *is* the offline bench, not the robot's real-time controller. Offline
  tooling — scenario generation, replay, metrics, regression gating — is Python
  work in every robotics shop.
- The expensive parts are already native. MuJoCo's physics is C, NumPy's math is
  C, and the perception models run in PyTorch. Python orchestrates; it does not
  do the arithmetic.
- Throughput comes from running scenarios in parallel across the 24 cores, not
  from single-run speed.

The boundary is worth stating plainly rather than glossing: a hard real-time
control loop on the physical robot would not be Python, and this demo does not
claim otherwise. It shows the offline half of the job, which is the half the
posting describes in the most detail.

### 4. Recording, replay, and recreation

Every run writes timestamped telemetry on a virtual clock, exactly as
`robot_sim.py` does: camera frames, detections, planned and executed
trajectories, joint states, gripper events, and the outcome of each attempt.

Three things then become possible:

- **Replay** — scrub a run and see what the robot saw and intended.
- **Recreation** — re-run *new code* against a recorded run. For a perception
  change, feed the recorded frames and ask whether the new model would have
  found the berry. For a planning change, restore the simulator to the recorded
  world state and re-plan.
- **Scenario mining** — every failure becomes a permanent regression case, so the
  corpus grows from real failures rather than from someone's imagination.

Determinism is a hard requirement: fixed seeds, fixed physics timestep, pinned
model versions. A bench that gives different answers on reruns proves nothing.

### 5. Metrics and instrumentation

Per pick attempt, a record with child spans for perceive, plan, execute, verify.
Dashboards for:

- pick success rate, bucketed by occlusion level and ripeness
- missed-ripe rate and false-pick rate
- damage events: neighbor knocked, stem torn, berry dropped
- p50 / p95 cycle time, and where the time goes
- a failure taxonomy, so "it is getting worse" becomes
  "unreachable-after-3-retries is up 40% on clustered berries"

This is the qualification the posting states most plainly: instrument a complex
system, find where it is weak, and act on it.

### 6. Regression gate

A pull request runs the scenario suite in parallel across the 24 cores and
reports a metrics diff against the baseline — lab-robot's `compare` command,
with a vector of metrics instead of one RMSE. Merge is blocked on a regression
in success rate or damage events, with a per-scenario breakdown.

A change that improves average success while introducing one new damage case
should be caught. That trade-off is the interesting conversation.

Two tiers, because the posting names both simulation and smoke testing as
separate steps:

- **Smoke** — six scenarios, a few seconds, run on every commit. Catches the
  change that breaks everything.
- **Full suite** — the whole corpus across 24 cores, run on a pull request.
  Catches the change that breaks one hard case.

The tiers exist so that the fast loop stays fast. A bench that takes twenty
minutes to answer stops being used.

### 7. Agentic development loop

1. An operations report arrives: "drops berries on shelf 3, afternoons."
2. An agent queries the telemetry index for matching runs — shelf 3, afternoon
   lighting, drop outcomes — and finds the cluster of failures.
3. It builds a minimal reproducing scenario and confirms the failure offline.
4. It proposes a change, runs the regression suite, and opens a PR with
   before/after metrics and a replay link for the failing case.
5. A human reviews the trade-off and the field test plan.

The agent never touches the robot. It works entirely through the bench, which is
the argument for building the bench.

### 8. From sim to field

Passing the suite is not the same as working on the robot, and a bench that
pretends otherwise is worse than no bench. So the loop has to close the other
way too.

- **A field-test plan comes out of the bench.** When a change passes, the bench
  emits what to watch during the field test: which scenarios the change
  affected, which metrics should move and by how much, and the specific failure
  it was supposed to fix.
- **The field records the same metrics.** Pick success, damage events, cycle
  time, failure taxonomy — identical schema, whether the run came from MuJoCo
  or from a real gutter.
- **The gap is a tracked number.** Predicted versus observed, per metric. That
  number says how much the bench can be trusted, and it is the honest answer to
  "why should we believe your simulator." When it widens, the simulator is
  wrong and the fix is in the scenario generator, not in the robot.

This is the part that serves the field-reliability half of the job. Operations
reports a problem, the bench reproduces it, the fix ships with a prediction, and
the field either confirms the prediction or exposes a gap in the model.

## Running it

**Home machine (RTX 5070 Ti 16GB, 24 cores, 30GB RAM)**

- MuJoCo physics is light enough to run many scenarios in parallel on CPU, with
  GPU rendering for synthetic data generation.
- Perception training: YOLO-seg small fits comfortably in 16GB.
- The scenario suite is what the 24 cores are for.
- Keep total usage near 20GB of the 30GB available.

Isaac Sim would look more impressive but is heavy for a 16GB card and adds setup
risk on demo day. MuJoCo is the safer choice; state the trade-off rather than
hiding it.

**Packaging**

Follow lab-robot: one Docker container that records a fresh session on start and
serves the replay page, with env vars for scenario count and seed, and assets
baked in so it runs with `--network none`. Plus `.claude/launch.json` so the
page opens in the browser pane during development.

**AWS (optional)**

A g5.xlarge spot instance to generate a large synthetic dataset or run the full
corpus faster than the home machine can. Terraform, up for a demo and torn down
after.

## Build order

1. **Sim cell + control loop.** Arm reaches a hardcoded berry pose and cuts.
   Nothing learned yet. Proves the `HarvestCell` interface and the physics.
2. **Telemetry + web replay.** A run can be replayed and watched. Early on
   purpose: everything later depends on it. Port `demo_export.py`'s observer and
   the `window.DEMO_DATA` page.
3. **Perception.** Synthetic data generation, training, evaluation on held-out
   layouts. The robot now finds its own targets.
4. **Metrics + scenario suite + regression gate.** Twenty scenarios, a metrics
   diff, a blocked PR.
5. **Recreation.** Re-run new perception code against old recordings.
6. **Hard cases.** Occlusion, clusters, retry policy. Show a metric moving
   because of a deliberate change.
7. **Agentic loop.** Failure report to PR, with the suite as the guardrail.

Stop after step 4 if time runs short. Steps 1-4 already demonstrate the sim,
replay, visualization, instrumentation, and pre-merge validation the posting
describes.

### Build it as a codebase that was inherited

The job is not greenfield. The posting asks to ramp up on an existing codebase
and own an area of it, and a demo built cleanly from scratch cannot show that.

So step 1 deliberately lands a **baseline that is good enough to run and bad
enough to improve**: a naive planner that approaches every berry head-on, a
fixed retry count, a ripeness threshold that is a hardcoded constant. It works.
It is also visibly wrong in ways the metrics will expose later.

Then steps 5 and 6 are the real story: pick one area, measure it, improve it,
and let the commit history show the loop. "Occluded-berry success went from 61%
to 84% by replacing the head-on approach with a peduncle-aligned one, at the
cost of 0.4 s of cycle time" is the sentence this demo exists to earn. It is
also exactly what the posting means by iterative improvement on a problem with
no defined correct answer.

The baseline is not padding. It is the thing being owned.

## Five-minute demo

1. A harvest run in the viewer: the arm works down a gutter, detections overlaid
   on the camera feed, berries picked and skipped.
2. A failure: a berry behind a leaf, three approach angles tried, given up.
   Scrub to the moment the planner ran out of options.
3. That failure, now a scenario in the corpus. Open the PR that fixes it.
4. Gate output: success rate up on occluded berries, but one new damage case
   appeared and the merge was blocked. Show the per-scenario diff.
5. The dashboard: cycle time and failure taxonomy over the last hundred runs.

## Open questions

- Which public real strawberry dataset, and under what license, for sim-to-real
  measurement. Verify before use.
- How faithful the peduncle cut has to be for a sim result to mean anything.
  There is a point past which more physics fidelity stops paying.
- Whether to model the linear rail and multi-shelf traversal, or keep the scope
  to one gutter.
- Whether to share code with lab-robot. A small common package for the config /
  observer / telemetry / replay-page pattern is tempting, but two demos that
  each stand alone are easier to show. Copy first; extract only if a third one
  appears.
