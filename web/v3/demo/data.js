window.DEMO = {
 "meta": {
  "generated": "2026-11-17 00:23 UTC",
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
   "peak_force_n": 0.0,
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
   "peak_force_n": 0.0,
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
   "peak_force_n": 0.0,
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
   "peak_force_n": 0.0,
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
   "peak_force_n": 0.0,
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
   "peak_force_n": 0.0,
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
   "outcome": "fruit_contact",
   "est_ripeness": 0.84,
   "peak_force_n": 0.2,
   "cycle_s": 2.5,
   "flags": [
    "fruit_contact"
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
   "peak_force_n": 0.0,
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
   "peak_force_n": 0.0,
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
   "outcome": "fruit_contact",
   "peak_force_n": 0.2,
   "cycle_s": 2.5,
   "field": "fruit_contact"
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
  "prompt": "You are working on the control software of a strawberry-harvesting robot: a 6-axis arm with a cutter.\n\nField report from harvester-01, gutter row G3:\n  pick p07 aborted: fruit_contact. The cutter touched a fruit with 0.2 N. It may touch only stems,\n  so the robot stopped, backed out and gave up the berry after 2.5 s.\n  The robot went for a ripe strawberry. An unripe strawberry hangs in front of it, over the ripe\n  one's top, where the stem is cut.\n\nEvery logged attempt has been rebuilt in a MuJoCo simulation from the robot's own RGB-D image.\nRun ./check.sh to see all ten, run with the robot code in this directory.\n\nYour task: change the robot's code so that p07 is picked, and the nine attempts that were\npicked still are.\n\nRules:\n- Change only src/harvest/robot_controller.py. The simulator (src/harvest/reproduce_scene.py)\n  and the data are the experiment; do not change them.\n- Keep the change small and easy to read.\n- When ./check.sh says \"10 of 10 attempts picked\", stop. Finish with a short explanation of\n  what was wrong and what you changed, then:\n  PR-TITLE: <one line>\n  PR-BODY:\n  <markdown: a few bullets>\n",
  "transcript": [
   {
    "t": 4,
    "tool": "Bash",
    "what": "*.py"
   },
   {
    "t": 7,
    "tool": "Bash",
    "what": "reproduce_scene.py && ls data models"
   },
   {
    "t": 9,
    "tool": "Read",
    "what": "robot_controller.py"
   },
   {
    "t": 9,
    "tool": "Read",
    "what": "reproduce_scene.py"
   },
   {
    "t": 12,
    "tool": "Bash",
    "what": "check.sh 2>&1 | tail -15"
   },
   {
    "t": 31,
    "tool": "Bash",
    "what": "show.py 2>&1 | tail -40"
   },
   {
    "t": 33,
    "say": "Inspecting the berries the camera found in each attempt, to see the geometry of p07."
   },
   {
    "t": 36,
    "tool": "Write",
    "what": "show.py"
   },
   {
    "t": 40,
    "tool": "Bash",
    "what": "show.py 2>&1 | tail -40"
   },
   {
    "t": 45,
    "tool": "Edit",
    "what": "show.py"
   },
   {
    "t": 46,
    "tool": "Bash",
    "what": "show.py"
   },
   {
    "t": 69,
    "tool": "Edit",
    "what": "robot_controller.py"
   },
   {
    "t": 70,
    "tool": "Bash",
    "what": "check.sh 2>&1 | tail -13"
   },
   {
    "t": 92,
    "say": "`./check.sh` now reports **10 of 10 attempts picked**. p07 is picked with 0.0 N on any fruit, and the other nine still pick as before (4.5 s each, 0.0 N). It also says \"9 of 10 end as they did in the field\". That's expected: p07 was a `fruit_contact` in the field and is now a pick.\n\n**What was wrong:** `plan()` always sent the cutter straight in along +y to the cut point, without looking at the other berries the camera had found. In p07 the unripe berry hangs right on that line, in front of the ripe one's stem, so the cutter hit it on the way in.\n\n**What I changed** (only `src/harvest/robot_controller.py`):\n- **New `path_is_clear()`:** checks whether the straight line from the start point to the cut point stays at least 15 mm (`CUTTER_CLEARANCE`) from every other berry. It treats each berry as an ellipsoid 1.4 times taller than wide, the same shape the rest of the code assumes.\n- **`plan()`:** tries a short list of ways in (`APPROACHES`: straight in, then 45\u00b0 to the left or right, then 90\u00b0) and uses the first clear one. If none is clear it falls back to straight in, which is the old behaviour.\n- **Effect on the others:** the nine attempts that already worked have a clear straight path, so their motion hasn't changed. p07 comes in at an angle, and its cycle takes 5.0 s instead of 4.5 s.\n\nI couldn't run my own diagnostic script here (Python outside `check.sh` needed approval), so I don't know which angle p07 used. I haven't committed anything.\n\nPR-TITLE: Approach the stem from the side when another berry is in the way\n\nPR-BODY:\n- **Problem:** the cutter always went straight in (+y) to the cut point. In p07 an unripe berry hangs on that line in front of the ripe one's stem, so the cutter touched it (0.2 N), and the robot stopped and gave up the berry.\n- **Fix:** `plan()` checks whether the approach line keeps `CUTTER_CLEARANCE` (15 mm) from every other berry, using `path_is_clear()`. If it doesn't, the cutter tries 45\u00b0 and then 90\u00b0 approaches from either side and uses the first clear one.\n- **No change for clear paths:** when the straight path is clear, which is true for the other nine attempts, the motion is exactly as before.\n- **Result:** `./check.sh` reports 10 of 10 attempts picked, with no fruit contact. p07's cycle goes from a 2.5 s abort to a 5.0 s pick."
   }
  ],
  "checks": [
   {
    "t": 24,
    "passed": false
   },
   {
    "t": 82,
    "passed": true
   }
  ],
  "text": "`./check.sh` now reports **10 of 10 attempts picked**. p07 is picked with 0.0 N on any fruit, and the other nine still pick as before (4.5 s each, 0.0 N). It also says \"9 of 10 end as they did in the field\". That's expected: p07 was a `fruit_contact` in the field and is now a pick.\n\n**What was wrong:** `plan()` always sent the cutter straight in along +y to the cut point, without looking at the other berries the camera had found. In p07 the unripe berry hangs right on that line, in front of the ripe one's stem, so the cutter hit it on the way in.\n\n**What I changed** (only `src/harvest/robot_controller.py`):\n- **New `path_is_clear()`:** checks whether the straight line from the start point to the cut point stays at least 15 mm (`CUTTER_CLEARANCE`) from every other berry. It treats each berry as an ellipsoid 1.4 times taller than wide, the same shape the rest of the code assumes.\n- **`plan()`:** tries a short list of ways in (`APPROACHES`: straight in, then 45\u00b0 to the left or right, then 90\u00b0) and uses the first clear one. If none is clear it falls back to straight in, which is the old behaviour.\n- **Effect on the others:** the nine attempts that already worked have a clear straight path, so their motion hasn't changed. p07 comes in at an angle, and its cycle takes 5.0 s instead of 4.5 s.\n\nI couldn't run my own diagnostic script here (Python outside `check.sh` needed approval), so I don't know which angle p07 used. I haven't committed anything.\n\nPR-TITLE: Approach the stem from the side when another berry is in the way\n\nPR-BODY:\n- **Problem:** the cutter always went straight in (+y) to the cut point. In p07 an unripe berry hangs on that line in front of the ripe one's stem, so the cutter touched it (0.2 N), and the robot stopped and gave up the berry.\n- **Fix:** `plan()` checks whether the approach line keeps `CUTTER_CLEARANCE` (15 mm) from every other berry, using `path_is_clear()`. If it doesn't, the cutter tries 45\u00b0 and then 90\u00b0 approaches from either side and uses the first clear one.\n- **No change for clear paths:** when the straight path is clear, which is true for the other nine attempts, the motion is exactly as before.\n- **Result:** `./check.sh` reports 10 of 10 attempts picked, with no fruit contact. p07's cycle goes from a 2.5 s abort to a 5.0 s pick.",
  "turns": 13,
  "seconds": 95,
  "cost_usd": 0.4433634,
  "exit": 0
 },
 "diff": [
  {
   "path": "src/harvest/robot_controller.py",
   "protected": false,
   "diff": "--- a/src/harvest/robot_controller.py\n+++ b/src/harvest/robot_controller.py\n@@ -46,13 +46,36 @@\n     return min(ripe, key=lambda b: np.linalg.norm((b.center - camera_axis)[[0, 2]]))\n \n \n+CUTTER_CLEARANCE = 0.015  # m the cutter keeps from any other fruit on its way in\n+\n+# Ways in, in order of preference: straight in, then turned ever more to the side.\n+APPROACHES = [np.array([np.sin(a), np.cos(a), 0.0]) for a in np.radians([0, 45, -45, 90, -90])]\n+\n+\n+def path_is_clear(start: np.ndarray, end: np.ndarray, berries: list[Berry]) -> bool:\n+    \"\"\"True if the straight line from start to end keeps CUTTER_CLEARANCE from every berry.\"\"\"\n+    for berry in berries:\n+        # Squash the berry's height so it becomes a sphere, and the line with it.\n+        scale = np.array([1.0, 1.0, 1.0 / 1.4])\n+        a, b, c = start * scale, end * scale, berry.center * scale\n+        t = np.clip(np.dot(c - a, b - a) / np.dot(b - a, b - a), 0.0, 1.0)\n+        if np.linalg.norm(a + t * (b - a) - c) < berry.radius + CUTTER_CLEARANCE:\n+            return False\n+    return True\n+\n+\n def plan(target: Berry, berries: list[Berry]) -> list[Waypoint]:\n-    \"\"\"Line up in front of the stem, go straight in, cut, and back out.\"\"\"\n+    \"\"\"Line up in front of the stem, go straight in, cut, and back out.\n+\n+    If another berry hangs in the way, come in from the side instead.\n+    \"\"\"\n     cut_point = target.top + [0.0, 0.0, CUT_ABOVE_TOP]\n-    forward = np.array([0.0, 1.0, 0.0])  # straight in, away from the robot\n-    start = cut_point - forward * APPROACH_DISTANCE\n+    others = [b for b in berries if b is not target]\n+    direction = next((d for d in APPROACHES if path_is_clear(cut_point - d * APPROACH_DISTANCE, cut_point, others)),\n+                     APPROACHES[0])\n+    start = cut_point - direction * APPROACH_DISTANCE\n     return [\n-        Waypoint(start, forward),\n-        Waypoint(cut_point, forward, cut=True),\n-        Waypoint(start, forward),\n+        Waypoint(start, direction),\n+        Waypoint(cut_point, direction, cut=True),\n+        Waypoint(start, direction),\n     ]\n",
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
   "cycle_s": 5.0,
   "field": "fruit_contact"
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
  "title": "Approach the stem from the side when another berry is in the way",
  "body": "- **Problem:** the cutter always went straight in (+y) to the cut point. In p07 an unripe berry hangs on that line in front of the ripe one's stem, so the cutter touched it (0.2 N), and the robot stopped and gave up the berry.\n- **Fix:** `plan()` checks whether the approach line keeps `CUTTER_CLEARANCE` (15 mm) from every other berry, using `path_is_clear()`. If it doesn't, the cutter tries 45\u00b0 and then 90\u00b0 approaches from either side and uses the first clear one.\n- **No change for clear paths:** when the straight path is clear, which is true for the other nine attempts, the motion is exactly as before.\n- **Result:** `./check.sh` reports 10 of 10 attempts picked, with no fruit contact. p07's cycle goes from a 2.5 s abort to a 5.0 s pick.",
  "explanation": "`./check.sh` now reports **10 of 10 attempts picked**. p07 is picked with 0.0 N on any fruit, and the other nine still pick as before (4.5 s each, 0.0 N). It also says \"9 of 10 end as they did in the field\". That's expected: p07 was a `fruit_contact` in the field and is now a pick.\n\n**What was wrong:** `plan()` always sent the cutter straight in along +y to the cut point, without looking at the other berries the camera had found. In p07 the unripe berry hangs right on that line, in front of the ripe one's stem, so the cutter hit it on the way in.\n\n**What I changed** (only `src/harvest/robot_controller.py`):\n- **New `path_is_clear()`:** checks whether the straight line from the start point to the cut point stays at least 15 mm (`CUTTER_CLEARANCE`) from every other berry. It treats each berry as an ellipsoid 1.4 times taller than wide, the same shape the rest of the code assumes.\n- **`plan()`:** tries a short list of ways in (`APPROACHES`: straight in, then 45\u00b0 to the left or right, then 90\u00b0) and uses the first clear one. If none is clear it falls back to straight in, which is the old behaviour.\n- **Effect on the others:** the nine attempts that already worked have a clear straight path, so their motion hasn't changed. p07 comes in at an angle, and its cycle takes 5.0 s instead of 4.5 s.\n\nI couldn't run my own diagnostic script here (Python outside `check.sh` needed approval), so I don't know which angle p07 used. I haven't committed anything.",
  "branch": "fix/approach-around-front-berry",
  "base": "main",
  "reviewer": "klahisaac"
 },
 "rules": {
  "force_limit_n": 0.05,
  "reach_mm": 5.0,
  "tool_speed_m_s": 0.1
 }
};
