"""
Visualize the final field for the coupled 2D advection example.
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np


DEFAULT_FIELD_FILE = Path(__file__).resolve().parent / "data" / "final_field.json"
DEFAULT_FRAMES_DIR = Path(__file__).resolve().parent / "data" / "pic"
DEFAULT_FRAMES_FILE = Path(__file__).resolve().parent / "data" / "frame_snapshots.json"
DEFAULT_PARTITIONS_FILE = Path(__file__).resolve().parent / "data" / "tile_partitions.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "advection_final.png"
DEFAULT_GIF = Path(__file__).resolve().parent / "advection_evolution.gif"


def render_field(
    field: np.ndarray,
    output_path: Path,
    step: Optional[int] = None,
    x_parts=None,
    y_parts=None,
):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Final field shape:", field.shape)
        return output_path

    fig, ax = plt.subplots(figsize=(7.2, 5.8))
    image = ax.imshow(field, origin="lower", cmap="viridis")
    title = "BeeMesh 2D Advection With Bee Tile Exchange"
    if step is not None:
        title += f"\nStep {step}"
    ax.set_title(title, fontsize=12, fontweight="semibold")
    ax.set_xlabel("Y Grid Index")
    ax.set_ylabel("X Grid Index")

    x_boundaries = [boundary[0] for boundary in (x_parts or [])[1:]]
    y_boundaries = [boundary[0] for boundary in (y_parts or [])[1:]]

    for x0 in x_boundaries:
        ax.axhline(
            x0 - 0.5,
            color="white",
            linewidth=1.0,
            alpha=0.85,
            linestyle=(0, (2, 2)),
        )
    for y0 in y_boundaries:
        ax.axvline(
            y0 - 0.5,
            color="white",
            linewidth=1.0,
            alpha=0.85,
            linestyle=(0, (2, 2)),
        )

    if x_boundaries or y_boundaries:
        ax.text(
            0.02,
            0.04,
            "Dotted lines show bee tile partitions",
            transform=ax.transAxes,
            fontsize=8.5,
            color="#f4f4f4",
            ha="left",
            va="bottom",
            bbox={"facecolor": "black", "alpha": 0.22, "pad": 3, "edgecolor": "none"},
        )

    fig.colorbar(image, ax=ax, label="u")
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)
    return output_path


def render_gif(frames_dir: Path, output_path: Path):
    frame_files = sorted(frames_dir.glob("frame_*.png"))
    if not frame_files:
        return None

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed. Skipping GIF generation.")
        return None

    images = [Image.open(frame_file) for frame_file in frame_files]
    try:
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            duration=180,
            loop=0,
        )
    finally:
        for image in images:
            image.close()
    return output_path


def rebuild_frames(frames_file: Path, partitions_file: Path, frames_dir: Path):
    if not frames_file.exists():
        return 0

    snapshots = json.loads(frames_file.read_text(encoding="utf-8"))
    partitions = {}
    if partitions_file.exists():
        partitions = json.loads(partitions_file.read_text(encoding="utf-8"))

    x_parts = partitions.get("x_parts", [])
    y_parts = partitions.get("y_parts", [])
    frames_dir.mkdir(parents=True, exist_ok=True)

    for existing in frames_dir.glob("frame_*.png"):
        existing.unlink()

    for index, snapshot in enumerate(snapshots):
        frame_file = frames_dir / f"frame_{index:03d}.png"
        render_field(
            np.asarray(snapshot["field"]),
            frame_file,
            step=snapshot.get("step"),
            x_parts=x_parts,
            y_parts=y_parts,
        )

    return len(snapshots)


def main():
    parser = argparse.ArgumentParser(description="Visualize BeeMesh advection output.")
    parser.add_argument("--field-file", default=str(DEFAULT_FIELD_FILE))
    parser.add_argument("--frames-dir", default=str(DEFAULT_FRAMES_DIR))
    parser.add_argument("--frames-file", default=str(DEFAULT_FRAMES_FILE))
    parser.add_argument("--partitions-file", default=str(DEFAULT_PARTITIONS_FILE))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gif-output", default=str(DEFAULT_GIF))
    args = parser.parse_args()

    rebuilt = rebuild_frames(
        Path(args.frames_file),
        Path(args.partitions_file),
        Path(args.frames_dir),
    )
    if rebuilt:
        print(f"Rebuilt {rebuilt} frame(s) in {Path(args.frames_dir)}")

    field = np.asarray(json.loads(Path(args.field_file).read_text(encoding="utf-8")))
    output_path = render_field(field, Path(args.output))
    print(f"Saved plot to {output_path}")
    gif_output = render_gif(Path(args.frames_dir), Path(args.gif_output))
    if gif_output is not None:
        print(f"Saved GIF to {gif_output}")


if __name__ == "__main__":
    main()
