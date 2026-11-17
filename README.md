# Strawberry harvest: from a field failure to a reviewed fix

A strawberry-harvesting robot fails one pick in the field. This project
rebuilds that attempt in a MuJoCo simulation from the robot's own log line and
RGB-D image, reproduces the failure with the robot's code as it was, lets an AI
agent fix the robot's controller against the simulation, reruns every logged
attempt, and writes the change up as a pull request.

**Demo:** https://harvest.isaacon.dev, a recorded run of every step. The site lists
every version of the demo: how each was built, what was wrong with it, and what
the next one improved. This README describes version 3, the current one.

## The failure

Harvester-01 makes ten attempts in gutter row G3. Nine are picked. In the
tenth, p07, an unripe berry hangs 70 mm in front of the ripe target, over its
top, where the stem is cut. The robot sends its cutter straight in and
touches the unripe berry. The cutter may touch only stems, since a strawberry
bruises easily, so the robot stops and backs out:

```json
{"pick": "p07", "event": "pick.aborted", "outcome": "fruit_contact", "peak_force_n": 0.2, "flags": ["fruit_contact"], ...}
```

Earlier versions had the berries fixed in place, so the same touch was a
51.8 N `collision` (version 2) or a `stem_torn` (version 1). With soft,
elastic stems the unripe berry swings aside instead, and the force is what a
hanging berry really pushes back with.

## How it works

```
Blender ──► RGB-D images + YOLO boxes ──► YOLO11n detector
   │
   └──► 10 field attempts (log line + RGB-D image)
                 │
                 ▼
        reproduce_scene.py: YOLO + depth → berries in 3D → MuJoCo scene
                 │            6-axis arm driven by robot_controller.py
                 ▼
        bake_demo.py: reproduce → agent fixes robot_controller.py → rerun → web/v3/demo/
```

1. **Data.** Blender (Cycles) renders a greenhouse gutter with strawberry
   clusters: 640x640 RGB, depth in millimetres, and exact YOLO boxes for ripe
   and unripe berries from the renderer's object index. The same renderer
   makes the ten field attempts and their log lines.
2. **Perception.** A YOLO11n model is fine-tuned on the Blender images to box
   each berry and say whether it is ripe.
3. **Simulation.** For each log line, the YOLO boxes and the depth image give
   each berry's position and size. The berries are placed in MuJoCo in front
   of a 6-axis arm with a cutter. Each berry hangs from an elastic rod, a
   MuJoCo 1D flexcomp that bends and twists, so a pushed berry swings aside.
   `robot_controller.py` picks the target and the cutter's waypoints, and the
   arm follows them with inverse kinematics. Any touch on a fruit (over
   0.05 N) is a `fruit_contact`, and the arm backs out; a cutter that ends off
   the cut point is a miss; otherwise the berry is picked.
4. **The fix.** A headless Claude Code agent gets the field report, a copy of
   the code and one command that reruns all ten attempts. It may change only
   `robot_controller.py`. When all ten are picked, its explanation and PR text
   go on the demo page.

The simulation must end every attempt the way the field did before the fix
means anything: with the original controller, nine are picked and p07 is a
fruit contact.

## Layout

| Path | What it is |
|---|---|
| `src/data_generator/blender_scene.py` | the Blender greenhouse renderer |
| `src/data_generator/make_dataset.py` | renders the YOLO training set |
| `src/data_generator/make_field_logs.py` | renders the ten field attempts and writes their log |
| `src/perception/strawberry_perception_trainer.py` | trains the YOLO detector |
| `src/harvest/robot_controller.py` | the robot's decisions: target and cutter path. The only file the agent edits |
| `src/harvest/reproduce_scene.py` | rebuilds each attempt in MuJoCo and runs the controller |
| `src/harvest/bake_demo.py` | runs every step, the agent included, and writes `web/v3/demo/` |
| `models/strawberry_yolo.pt` | the trained detector |
| `web/` | the static demo site: a list of every version, with each version's page in `web/v1/` to `web/v3/` |
| `scripts/deploy_pages.py` | uploads `web/` to Cloudflare Pages |

## Running it

You need [uv](https://docs.astral.sh/uv/), an NVIDIA GPU for rendering and
training, and, for the agent step, the
[Claude Code](https://docs.anthropic.com/en/docs/claude-code) CLI signed in.
`data/` and `runs/` are not tracked, so start by making the data.

Make the training images and the field attempts. Blender's `bpy` wheel needs
Python 3.11, so these run as standalone uv scripts:

```bash
uv run --script src/data_generator/make_dataset.py --count 200
```

```bash
uv run --script src/data_generator/make_field_logs.py
```

Train the detector (writes `models/strawberry_yolo.pt`):

```bash
uv run python src/perception/strawberry_perception_trainer.py
```

Rerun all ten attempts in the simulator with the current controller:

```bash
uv run python src/harvest/reproduce_scene.py
```

Run every step, the agent included, and rebuild the demo page:

```bash
MUJOCO_GL=egl uv run --group demo python src/harvest/bake_demo.py
```

Add `--no-agent` to reuse the agent's last run. To view the page locally:

```bash
python3 -m http.server 8848 -d web
```
