"""Train a YOLO model that finds ripe (and unripe) strawberries in RGB images.

    uv run --group train python src/perception/strawberry_perception_trainer.py

The training data is the Blender dataset from src/data_generator/make_dataset.py:
640x640 RGB images with YOLO boxes in two classes, 0 ripe and 1 unripe. The
unripe class is kept because an unripe berry in the cutter's way matters too.

The best weights are copied to models/strawberry_yolo.pt, and the scores on
the validation images are printed at the end.
"""

import argparse
import pathlib
import shutil

import ultralytics

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "data" / "dataset" / "data.yaml"
RUNS = ROOT / "runs" / "perception"
WEIGHTS = ROOT / "models" / "strawberry_yolo.pt"


def train(base_model: str, epochs: int, batch: int) -> pathlib.Path:
    """Fine-tune a pretrained YOLO model on the strawberry dataset; return the best weights."""
    model = ultralytics.YOLO(base_model)
    result = model.train(
        data=str(DATA),
        epochs=epochs,
        imgsz=640,
        batch=batch,
        project=str(RUNS),
        name="train",
        exist_ok=True,
        workers=4,
        seed=0,
        fliplr=0.5,  # berries look the same mirrored; no up-down flip, they hang down
    )
    return pathlib.Path(result.save_dir) / "weights" / "best.pt"


def report(weights: pathlib.Path) -> None:
    """Print precision, recall and mAP on the validation images, per class."""
    metrics = ultralytics.YOLO(str(weights)).val(data=str(DATA), imgsz=640, project=str(RUNS), name="val",
                                                 exist_ok=True, verbose=False)
    print(f"\n{'class':<8} {'precision':>9} {'recall':>7} {'mAP50':>7} {'mAP50-95':>9}")
    for index, name in metrics.names.items():
        precision, recall, map50, map50_95 = metrics.class_result(index)
        print(f"{name:<8} {precision:9.3f} {recall:7.3f} {map50:7.3f} {map50_95:9.3f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default="yolo11n.pt", help="pretrained YOLO model to start from")
    parser.add_argument("--epochs", type=int, default=100, help="passes over the training images")
    parser.add_argument("--batch", type=int, default=16, help="images per training step")
    args = parser.parse_args()

    best = train(args.model, args.epochs, args.batch)
    WEIGHTS.parent.mkdir(exist_ok=True)
    shutil.copy(best, WEIGHTS)
    print(f"\nweights: {WEIGHTS.relative_to(ROOT)}")
    report(WEIGHTS)


if __name__ == "__main__":
    main()
