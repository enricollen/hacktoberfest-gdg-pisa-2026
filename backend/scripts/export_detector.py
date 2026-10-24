"""Export the prompt-free YOLOE detector to ONNX (with NMS) for the torch-free runtime.

Only needed to regenerate models/yoloe-26s-seg-pf.onnx:

    uv run --group export python -m scripts.export_detector
    uv sync   # drops torch & ultralytics again
"""

import shutil

from ultralytics import YOLOE

from app.config import get_settings


def main() -> None:
    settings = get_settings()
    settings.models_dir.mkdir(parents=True, exist_ok=True)
    weights = settings.models_dir / settings.detector_model.replace(".onnx", ".pt")
    model = YOLOE(str(weights))
    exported = model.export(
        format="onnx", imgsz=settings.detector_imgsz, nms=True, simplify=True, dynamic=False
    )
    target = settings.models_dir / settings.detector_model
    if str(exported) != str(target):
        shutil.move(exported, target)
    print(f"Exported {target}")


if __name__ == "__main__":
    main()
