"""Timestamped records of what the robot saw, intended and did.

One record per meaningful step, carrying the simulator's own clock. This is the
file a failure investigation starts from, and what the demo's field log shows.
lab-robot writes the same shape to `telemetry.jsonl`; the comment there notes
that the same records go to Kafka in its Phase 2, and the same applies here.
"""

from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class Telemetry:
    robot_id: str = "harvester-01"
    records: list[dict] = field(default_factory=list)

    def event(self, t: float, event: str, detail: str = "", **extra) -> dict:
        rec = {
            "robot_id": self.robot_id,
            "t": round(float(t), 3),
            "event": event,
            "detail": detail,
            **extra,
        }
        self.records.append(rec)
        return rec

    def write_jsonl(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for rec in self.records:
                f.write(json.dumps(rec) + "\n")
        return path
