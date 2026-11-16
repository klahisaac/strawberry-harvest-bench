window.DEMO = {
 "meta": {
  "generated": "2026-11-16 14:57 UTC",
  "versions": {
   "mujoco": "4.0.0",
   "python": "3.12.16",
   "claude_code": "2.1.323"
  }
 },
 "logs": [
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p01",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.9,
   "peak_force_n": 0.5,
   "cycle_s": 4.6,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:00:00+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p02",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.89,
   "peak_force_n": 0.5,
   "cycle_s": 4.9,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:00:10+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p03",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.91,
   "peak_force_n": 0.7,
   "cycle_s": 4.7,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:00:21+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p04",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.89,
   "peak_force_n": 0.4,
   "cycle_s": 4.6,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:00:33+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p05",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.95,
   "peak_force_n": 0.5,
   "cycle_s": 4.3,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:00:43+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p06",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.92,
   "peak_force_n": 0.7,
   "cycle_s": 4.4,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:00:53+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p07",
   "event": "pick.aborted",
   "outcome": "collision",
   "est_ripeness": 0.84,
   "peak_force_n": 51.8,
   "cycle_s": 3.3,
   "flags": [
    "force_limit"
   ],
   "abnormal": true,
   "time": "2026-11-09T06:01:05+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p08",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.9,
   "peak_force_n": 0.1,
   "cycle_s": 4.7,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:01:13+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p09",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.88,
   "peak_force_n": 0.7,
   "cycle_s": 4.5,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:01:25+00:00"
  },
  {
   "robot": "harvester-01",
   "row": "G3",
   "pick": "p10",
   "event": "pick.completed",
   "outcome": "picked",
   "est_ripeness": 0.9,
   "peak_force_n": 0.0,
   "cycle_s": 4.6,
   "flags": [],
   "abnormal": false,
   "time": "2026-11-09T06:01:36+00:00"
  }
 ],
 "failed_pick": "p07",
 "camera": {
  "width": 640,
  "height": 640,
  "fx": 600.0,
  "fy": 600.0,
  "cx": 319.5,
  "cy": 319.5,
  "depth_unit_m": 0.001,
  "depth_axis": "optical axis (z), 0 = no hit"
 },
 "found": [
  {
   "ripe": false,
   "target": false,
   "center": [
    0.002,
    0.431,
    0.49
   ],
   "radius_mm": 15.6,
   "box": [
    285.4,
    163.1,
    364.9,
    284.7
   ],
   "confidence": 0.96
  },
  {
   "ripe": false,
   "target": false,
   "center": [
    -0.035,
    0.511,
    0.46
   ],
   "radius_mm": 11.9,
   "box": [
    233.3,
    271.2,
    278.1,
    332.2
   ],
   "confidence": 0.96
  },
  {
   "ripe": false,
   "target": false,
   "center": [
    0.035,
    0.521,
    0.495
   ],
   "radius_mm": 12.1,
   "box": [
    359.7,
    207.4,
    403.9,
    273.2
   ],
   "confidence": 0.95
  },
  {
   "ripe": true,
   "target": true,
   "center": [
    0.0,
    0.502,
    0.458
   ],
   "radius_mm": 19.6,
   "box": [
    281.4,
    256.2,
    359.2,
    351.9
   ],
   "confidence": 0.94
  }
 ],
 "before": [
  {
   "pick": "p01",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p02",
   "berries": 2,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p03",
   "berries": 2,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p04",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p05",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p06",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p07",
   "berries": 4,
   "outcome": "collision",
   "peak_force_n": 51.8,
   "cycle_s": 3.3,
   "field": "collision"
  },
  {
   "pick": "p08",
   "berries": 2,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p09",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p10",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  }
 ],
 "agent": {
  "model": "claude-opus-5-5",
  "prompt": "You are working on the control software of a strawberry-harvesting robot: a 6-axis arm with a cutter.\n\nField report from harvester-01, gutter row G3:\n  pick p07 aborted: collision. Peak force on fruit 51.8 N, over the 5 N limit; the robot stopped\n  the attempt after 3.3 s.\n  The robot went for a ripe strawberry. An unripe strawberry hangs in front of it, over the ripe\n  one's top, where the stem is cut.\n\nEvery logged attempt has been rebuilt in a MuJoCo simulation from the robot's own RGB-D image.\nRun ./check.sh to see all ten, run with the robot code in this directory.\n\nYour task: change the robot's code so that p07 is picked, and the nine attempts that were\npicked still are.\n\nRules:\n- Change only src/harvest/robot_controller.py. The simulator (src/harvest/reproduce_scene.py)\n  and the data are the experiment; do not change them.\n- Keep the change small and easy to read.\n- When ./check.sh says \"10 of 10 attempts picked\", stop. Finish with a short explanation of\n  what was wrong and what you changed, then:\n  PR-TITLE: <one line>\n  PR-BODY:\n  <markdown: a few bullets>\n",
  "transcript": [
   {
    "t": 6,
    "tool": "Bash",
    "what": "robot_controller.py"
   },
   {
    "t": 8,
    "tool": "Bash",
    "what": "reproduce_scene.py"
   },
   {
    "t": 24,
    "tool": "Bash",
    "what": "dump.py 2>&1 | tail -40"
   },
   {
    "t": 29,
    "tool": "Write",
    "what": "dump.py"
   },
   {
    "t": 31,
    "tool": "Bash",
    "what": "dump.py 2>&1 | tail -45"
   },
   {
    "t": 35,
    "tool": "Bash",
    "what": "dump.py"
   },
   {
    "t": 42,
    "say": "I can't run my own scripts here, only `./check.sh`. So first I'll add a temporary print to the planner and use check.sh to show me the berry positions in p07."
   },
   {
    "t": 43,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 44,
    "tool": "Bash",
    "what": "check.sh 2>&1"
   },
   {
    "t": 79,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 80,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 81,
    "tool": "Bash",
    "what": "check.sh 2>&1"
   },
   {
    "t": 99,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 100,
    "tool": "Bash",
    "what": "check.sh 2>&1"
   },
   {
    "t": 135,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 136,
    "tool": "Bash",
    "what": "check.sh 2>&1 | grep -A3 -B3 DBG"
   },
   {
    "t": 172,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 173,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 174,
    "tool": "Bash",
    "what": "check.sh 2>&1"
   },
   {
    "t": 221,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 223,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 224,
    "tool": "Bash",
    "what": "check.sh 2>&1"
   },
   {
    "t": 235,
    "say": "10 of 10 attempts picked. Here's the final diff:"
   },
   {
    "t": 236,
    "tool": "Bash",
    "what": "robot_controller.py"
   },
   {
    "t": 238,
    "tool": "Read",
    "what": "robot_controller.py"
   },
   {
    "t": 249,
    "say": "`./check.sh` now reports **10 of 10 attempts picked**. p07 is picked with 0.0 N on any fruit (4.9 s cycle), and the other nine are still picked exactly as before. The p07 row is marked \"differs from the field\" because it no longer ends in a collision.\n\n**What was wrong:** `plan()` takes `berries` as an argument but never used it. It always sent the cutter straight in along +y to a point 12 mm above the target's top, without checking whether anything was in the way. In p07 an unripe berry hangs 7 cm in front of the ripe one at cut height (z 0.49 against 0.498), right on that path. The cutter ran into it and hit 51.8 N.\n\n**What I changed** (only `src/harvest/robot_controller.py`):\n- **New `is_clear()`:** checks whether the cutter's straight path stays at least `CUTTER_CLEARANCE` (2 cm) from every other berry. Each berry is treated as a sphere at its full height (1.4 \u00d7 radius), which errs on the safe side.\n- **Approach angle in `plan()`:** it tries `APPROACH_ANGLES = (0, 20, -20, 40, -40)` degrees and takes the first one with a clear path. 0\u00b0 is the old straight-in path, so nothing changes for any attempt with a clear path, which is why the other nine behave identically. For p07 it picks 40\u00b0 from the left.\n- **Why not from above:** I tried that first and it failed. Tilting the cutter down puts the wrist about 0.68 m from the shoulder, more than the 0.60 m upper arm plus forearm can reach. At 45\u00b0 the IK diverged and the simulation blew up; at 40\u00b0 the tip lagged 8 cm low and still hit the unripe berry. The comment on `APPROACH_ANGLES` records this.\n\nTo find the blocker and the IK failure I added temporary debug prints to the controller. They're removed; the file holds only the change above.\n\nPR-TITLE: Approach the stem from the side when another berry blocks the straight path\n\nPR-BODY:\n- **Bug:** `plan()` ignored the other berries and always sent the cutter straight in. In p07 an unripe berry hangs in front of the target's stem, so the cutter hit it (51.8 N, attempt aborted).\n- **Fix:** a new `is_clear()` checks that the cutter's path keeps 2 cm from every other berry. `plan()` tries straight in first, then \u00b120\u00b0 and \u00b140\u00b0 from the side, and takes the first clear path.\n- **Not from above:** tilting the cutter down pushes the wrist out of the arm's reach, and the IK fails. The comment on `APPROACH_ANGLES` says so.\n- **Result:** `./check.sh` gives 10 of 10 attempts picked. p07 is picked with 0.0 N on any fruit, and the nine attempts that already worked keep the unchanged straight-in path."
   }
  ],
  "checks": [
   {
    "t": 17,
    "passed": false
   },
   {
    "t": 53,
    "passed": false
   },
   {
    "t": 90,
    "passed": false
   },
   {
    "t": 109,
    "passed": false
   },
   {
    "t": 145,
    "passed": false
   },
   {
    "t": 183,
    "passed": false
   },
   {
    "t": 232,
    "passed": true
   }
  ],
  "text": "`./check.sh` now reports **10 of 10 attempts picked**. p07 is picked with 0.0 N on any fruit (4.9 s cycle), and the other nine are still picked exactly as before. The p07 row is marked \"differs from the field\" because it no longer ends in a collision.\n\n**What was wrong:** `plan()` takes `berries` as an argument but never used it. It always sent the cutter straight in along +y to a point 12 mm above the target's top, without checking whether anything was in the way. In p07 an unripe berry hangs 7 cm in front of the ripe one at cut height (z 0.49 against 0.498), right on that path. The cutter ran into it and hit 51.8 N.\n\n**What I changed** (only `src/harvest/robot_controller.py`):\n- **New `is_clear()`:** checks whether the cutter's straight path stays at least `CUTTER_CLEARANCE` (2 cm) from every other berry. Each berry is treated as a sphere at its full height (1.4 \u00d7 radius), which errs on the safe side.\n- **Approach angle in `plan()`:** it tries `APPROACH_ANGLES = (0, 20, -20, 40, -40)` degrees and takes the first one with a clear path. 0\u00b0 is the old straight-in path, so nothing changes for any attempt with a clear path, which is why the other nine behave identically. For p07 it picks 40\u00b0 from the left.\n- **Why not from above:** I tried that first and it failed. Tilting the cutter down puts the wrist about 0.68 m from the shoulder, more than the 0.60 m upper arm plus forearm can reach. At 45\u00b0 the IK diverged and the simulation blew up; at 40\u00b0 the tip lagged 8 cm low and still hit the unripe berry. The comment on `APPROACH_ANGLES` records this.\n\nTo find the blocker and the IK failure I added temporary debug prints to the controller. They're removed; the file holds only the change above.\n\nPR-TITLE: Approach the stem from the side when another berry blocks the straight path\n\nPR-BODY:\n- **Bug:** `plan()` ignored the other berries and always sent the cutter straight in. In p07 an unripe berry hangs in front of the target's stem, so the cutter hit it (51.8 N, attempt aborted).\n- **Fix:** a new `is_clear()` checks that the cutter's path keeps 2 cm from every other berry. `plan()` tries straight in first, then \u00b120\u00b0 and \u00b140\u00b0 from the side, and takes the first clear path.\n- **Not from above:** tilting the cutter down pushes the wrist out of the arm's reach, and the IK fails. The comment on `APPROACH_ANGLES` says so.\n- **Result:** `./check.sh` gives 10 of 10 attempts picked. p07 is picked with 0.0 N on any fruit, and the nine attempts that already worked keep the unchanged straight-in path.",
  "turns": 24,
  "seconds": 251,
  "cost_usd": 0.83049,
  "exit": 0
 },
 "diff": [
  {
   "path": "src/harvest/robot_controller.py",
   "protected": false,
   "diff": "--- a/src/harvest/robot_controller.py\n+++ b/src/harvest/robot_controller.py\n@@ -13,6 +13,10 @@\n \n CUT_ABOVE_TOP = 0.012  # the stem is cut this far above the top of the fruit\n APPROACH_DISTANCE = 0.12  # the cutter lines up this far in front of the stem\n+CUTTER_CLEARANCE = 0.02  # m the cutter's path keeps from the surface of any other berry\n+# Degrees from straight in, tried in turn until the path is clear: positive comes from the left.\n+# Not from above: tilting the cutter down puts the wrist out of the arm's reach.\n+APPROACH_ANGLES = (0, 20, -20, 40, -40)\n \n \n @dataclasses.dataclass\n@@ -46,13 +50,32 @@\n     return min(ripe, key=lambda b: np.linalg.norm((b.center - camera_axis)[[0, 2]]))\n \n \n+def is_clear(start: np.ndarray, end: np.ndarray, others: list[Berry]) -> bool:\n+    \"\"\"Whether the cutter can move from start to end without touching any of the other berries.\"\"\"\n+    for berry in others:\n+        # The point of the path nearest the berry's centre.\n+        t = np.clip(np.dot(berry.center - start, end - start) / np.dot(end - start, end - start), 0.0, 1.0)\n+        nearest = start + t * (end - start)\n+        if np.linalg.norm(berry.center - nearest) < 1.4 * berry.radius + CUTTER_CLEARANCE:\n+            return False\n+    return True\n+\n+\n def plan(target: Berry, berries: list[Berry]) -> list[Waypoint]:\n-    \"\"\"Line up in front of the stem, go straight in, cut, and back out.\"\"\"\n+    \"\"\"Line up in front of the stem, go straight in, cut, and back out.\n+\n+    If another berry is in the way, come in at an angle from the side instead, as small\n+    an angle as clears it.\n+    \"\"\"\n     cut_point = target.top + [0.0, 0.0, CUT_ABOVE_TOP]\n-    forward = np.array([0.0, 1.0, 0.0])  # straight in, away from the robot\n-    start = cut_point - forward * APPROACH_DISTANCE\n+    others = [b for b in berries if b is not target]\n+    for angle in np.radians(APPROACH_ANGLES):\n+        direction = np.array([np.sin(angle), np.cos(angle), 0.0])  # in, turned sideways by the angle\n+        start = cut_point - direction * APPROACH_DISTANCE\n+        if is_clear(start, cut_point, others):\n+            break\n     return [\n-        Waypoint(start, forward),\n-        Waypoint(cut_point, forward, cut=True),\n-        Waypoint(start, forward),\n+        Waypoint(start, direction),\n+        Waypoint(cut_point, direction, cut=True),\n+        Waypoint(start, direction),\n     ]\n",
   "added": 29,
   "removed": 6
  }
 ],
 "after": [
  {
   "pick": "p01",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p02",
   "berries": 2,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p03",
   "berries": 2,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p04",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p05",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p06",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p07",
   "berries": 4,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.9,
   "field": "collision"
  },
  {
   "pick": "p08",
   "berries": 2,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p09",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  },
  {
   "pick": "p10",
   "berries": 3,
   "outcome": "picked",
   "peak_force_n": 0.0,
   "cycle_s": 4.5,
   "field": "picked"
  }
 ],
 "pr": {
  "title": "Approach the stem from the side when another berry blocks the straight path",
  "body": "- **Bug:** `plan()` ignored the other berries and always sent the cutter straight in. In p07 an unripe berry hangs in front of the target's stem, so the cutter hit it (51.8 N, attempt aborted).\n- **Fix:** a new `is_clear()` checks that the cutter's path keeps 2 cm from every other berry. `plan()` tries straight in first, then \u00b120\u00b0 and \u00b140\u00b0 from the side, and takes the first clear path.\n- **Not from above:** tilting the cutter down pushes the wrist out of the arm's reach, and the IK fails. The comment on `APPROACH_ANGLES` says so.\n- **Result:** `./check.sh` gives 10 of 10 attempts picked. p07 is picked with 0.0 N on any fruit, and the nine attempts that already worked keep the unchanged straight-in path.",
  "explanation": "`./check.sh` now reports **10 of 10 attempts picked**. p07 is picked with 0.0 N on any fruit (4.9 s cycle), and the other nine are still picked exactly as before. The p07 row is marked \"differs from the field\" because it no longer ends in a collision.\n\n**What was wrong:** `plan()` takes `berries` as an argument but never used it. It always sent the cutter straight in along +y to a point 12 mm above the target's top, without checking whether anything was in the way. In p07 an unripe berry hangs 7 cm in front of the ripe one at cut height (z 0.49 against 0.498), right on that path. The cutter ran into it and hit 51.8 N.\n\n**What I changed** (only `src/harvest/robot_controller.py`):\n- **New `is_clear()`:** checks whether the cutter's straight path stays at least `CUTTER_CLEARANCE` (2 cm) from every other berry. Each berry is treated as a sphere at its full height (1.4 \u00d7 radius), which errs on the safe side.\n- **Approach angle in `plan()`:** it tries `APPROACH_ANGLES = (0, 20, -20, 40, -40)` degrees and takes the first one with a clear path. 0\u00b0 is the old straight-in path, so nothing changes for any attempt with a clear path, which is why the other nine behave identically. For p07 it picks 40\u00b0 from the left.\n- **Why not from above:** I tried that first and it failed. Tilting the cutter down puts the wrist about 0.68 m from the shoulder, more than the 0.60 m upper arm plus forearm can reach. At 45\u00b0 the IK diverged and the simulation blew up; at 40\u00b0 the tip lagged 8 cm low and still hit the unripe berry. The comment on `APPROACH_ANGLES` records this.\n\nTo find the blocker and the IK failure I added temporary debug prints to the controller. They're removed; the file holds only the change above.",
  "branch": "fix/approach-around-front-berry",
  "base": "main",
  "reviewer": "klahisaac"
 },
 "rules": {
  "force_limit_n": 5.0,
  "reach_mm": 5.0,
  "tool_speed_m_s": 0.1
 }
};
