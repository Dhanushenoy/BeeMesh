"""
Visualize the periodic acoustic pulse output for the BeeMesh structured-grid demo.
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

import numpy as np


DEFAULT_FIELD_FILE = Path(__file__).resolve().parent / "data" / "final_field.json"
DEFAULT_FRAMES_DIR = Path(__file__).resolve().parent / "data" / "pic"
DEFAULT_FRAMES_FILE = Path(__file__).resolve().parent / "data" / "frame_snapshots.json"
DEFAULT_PARTITIONS_FILE = Path(__file__).resolve().parent / "data" / "tile_partitions.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "acoustic_pulse_final.png"
DEFAULT_GIF = Path(__file__).resolve().parent / "acoustic_pulse_evolution.gif"
DEFAULT_MP4 = Path(__file__).resolve().parent / "acoustic_pulse_evolution.mp4"


def render_field(
    field: np.ndarray,
    output_path: Path,
    step: Optional[int] = None,
    x_parts=None,
    y_parts=None,
    partition_overlays=None,
    step_history=None,
):
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib not installed. Final field shape:", field.shape)
        return output_path

    fig, (ax_field, ax_ts) = plt.subplots(
        1,
        2,
        figsize=(13.2, 5.8),
        gridspec_kw={"width_ratios": [1.55, 0.95]},
    )
    fig.patch.set_facecolor("black")
    ax_field.set_facecolor("black")
    ax_ts.set_facecolor("black")

    vmax = max(float(np.max(np.abs(field))), 1e-8)
    image = ax_field.imshow(
        field,
        origin="lower",
        cmap="coolwarm",
        vmin=-vmax,
        vmax=vmax,
    )

    x_boundaries = [boundary[0] for boundary in (x_parts or [])[1:]]
    y_boundaries = [boundary[0] for boundary in (y_parts or [])[1:]]
    for x0 in x_boundaries:
        ax_field.axhline(
            x0 - 0.5,
            color="white",
            linewidth=1.0,
            alpha=0.85,
            linestyle=(0, (2, 2)),
        )
    for y0 in y_boundaries:
        ax_field.axvline(
            y0 - 0.5,
            color="white",
            linewidth=1.0,
            alpha=0.85,
            linestyle=(0, (2, 2)),
        )

    for overlay in partition_overlays or []:
        x0 = float(overlay.get("x0", 0))
        x1 = float(overlay.get("x1", 0))
        y0 = float(overlay.get("y0", 0))
        y1 = float(overlay.get("y1", 0))
        hostname = overlay.get("hostname") or overlay.get("worker_id") or "unassigned"
        display_name = hostname[:-4] if hostname.endswith("-bee") else hostname
        ax_field.text(
            y0 + 1.0,
            x1 - 1.0,
            display_name,
            fontsize=10.2,
            color="white",
            alpha=0.82,
            ha="left",
            va="top",
            bbox={"facecolor": "black", "alpha": 0.18, "pad": 1.8, "edgecolor": "none"},
        )

    title = "BeeMesh Periodic Acoustic Pulse"
    if step is not None:
        title += f"\nStep {step}"
    ax_field.set_title(title, color="white", fontsize=12, fontweight="semibold")
    ax_field.set_xlabel("Y Grid Index", color="white")
    ax_field.set_ylabel("X Grid Index", color="white")
    ax_field.tick_params(colors="white")
    for spine in ax_field.spines.values():
        spine.set_color("white")
    ax_field.text(
        0.02,
        0.04,
        "Periodic pressure pulse with Hive-managed ghosted strip exchange",
        transform=ax_field.transAxes,
        fontsize=9.2,
        color="white",
        ha="left",
        va="bottom",
        bbox={"facecolor": "black", "alpha": 0.26, "pad": 3, "edgecolor": "none"},
    )

    steps = [entry.get("step") for entry in (step_history or [])]
    overhead = [
        1000.0 * float(entry.get("network_overhead_s", 0.0) or 0.0)
        for entry in (step_history or [])
    ]
    pings = [
        1000.0 * float(entry.get("hive_ping_s", 0.0) or 0.0)
        for entry in (step_history or [])
    ]
    if steps:
        ax_ts.plot(steps, overhead, color="#f4a261", linewidth=2.0, label="Network overhead")
        ax_ts.plot(steps, pings, color="#e76f51", linewidth=1.5, alpha=0.9, label="Hive ping")
        if step is not None:
            ax_ts.axvline(step, color="white", linewidth=1.1, alpha=0.8, linestyle=(0, (2, 2)))
        ax_ts.set_xlim(0, max(steps))
        ax_ts.set_title("Per-step link timing", color="white", fontsize=11, fontweight="semibold")
        ax_ts.set_xlabel("Step", color="white")
        ax_ts.set_ylabel("Milliseconds", color="white")
        ax_ts.tick_params(colors="white")
        ax_ts.grid(alpha=0.18, linestyle=":")
        legend = ax_ts.legend(loc="upper right", fontsize=8, frameon=False)
        for text in legend.get_texts():
            text.set_color("white")
    else:
        ax_ts.text(
            0.5,
            0.5,
            "No timing data",
            ha="center",
            va="center",
            color="white",
            transform=ax_ts.transAxes,
        )
        ax_ts.set_axis_off()

    for spine in ax_ts.spines.values():
        spine.set_color("white")

    cbar = fig.colorbar(image, ax=ax_field, fraction=0.046, pad=0.04)
    cbar.set_label("Pressure", color="white")
    cbar.ax.tick_params(colors="white")
    cbar.outline.set_edgecolor("white")

    fig.tight_layout()
    fig.savefig(output_path, dpi=220)
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
            duration=45,
            loop=0,
        )
    finally:
        for image in images:
            image.close()
    return output_path


def render_mp4(frames_dir: Path, output_path: Path, fps: int = 50):
    frame_pattern = frames_dir / "frame_%03d.png"
    if not any(frames_dir.glob("frame_*.png")):
        return None

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(frame_pattern),
            "-pix_fmt",
            "yuv420p",
            "-vcodec",
            "libx264",
            str(output_path),
        ]
        try:
            subprocess.run(
                command,
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return output_path
        except subprocess.CalledProcessError:
            pass

    print("ffmpeg not installed or MP4 encoding failed. Skipping MP4 generation.")
    return None


def rebuild_frames(
    frames_file: Path,
    partitions_file: Path,
    history_file: Path,
    frames_dir: Path,
):
    if not frames_file.exists():
        return 0

    snapshots = json.loads(frames_file.read_text(encoding="utf-8"))
    partitions = {}
    if partitions_file.exists():
        partitions = json.loads(partitions_file.read_text(encoding="utf-8"))
    step_history = []
    if history_file.exists():
        step_history = json.loads(history_file.read_text(encoding="utf-8"))

    x_parts = partitions.get("x_parts", [])
    y_parts = partitions.get("y_parts", [])
    partition_overlays = partitions.get("partition_overlays", [])
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
            partition_overlays=partition_overlays,
            step_history=step_history,
        )

    return len(snapshots)


def main():
    parser = argparse.ArgumentParser(description="Visualize BeeMesh periodic acoustic pulse output.")
    parser.add_argument("--field-file", default=str(DEFAULT_FIELD_FILE))
    parser.add_argument("--frames-dir", default=str(DEFAULT_FRAMES_DIR))
    parser.add_argument("--frames-file", default=str(DEFAULT_FRAMES_FILE))
    parser.add_argument("--partitions-file", default=str(DEFAULT_PARTITIONS_FILE))
    parser.add_argument(
        "--history-file",
        default=str(Path(__file__).resolve().parent / "data" / "step_history.json"),
    )
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--gif-output", default=str(DEFAULT_GIF))
    parser.add_argument("--mp4-output", default=str(DEFAULT_MP4))
    args = parser.parse_args()

    rebuilt = rebuild_frames(
        Path(args.frames_file),
        Path(args.partitions_file),
        Path(args.history_file),
        Path(args.frames_dir),
    )
    if rebuilt:
        print(f"Rebuilt {rebuilt} frame(s) in {Path(args.frames_dir)}")

    field = np.asarray(json.loads(Path(args.field_file).read_text(encoding="utf-8")))
    partitions = {}
    partitions_file = Path(args.partitions_file)
    if partitions_file.exists():
        partitions = json.loads(partitions_file.read_text(encoding="utf-8"))
    step_history = []
    history_file = Path(args.history_file)
    if history_file.exists():
        step_history = json.loads(history_file.read_text(encoding="utf-8"))

    output_path = render_field(
        field,
        Path(args.output),
        x_parts=partitions.get("x_parts", []),
        y_parts=partitions.get("y_parts", []),
        partition_overlays=partitions.get("partition_overlays", []),
        step_history=step_history,
    )
    print(f"Saved plot to {output_path}")
    gif_output = render_gif(Path(args.frames_dir), Path(args.gif_output))
    if gif_output is not None:
        print(f"Saved GIF to {gif_output}")
    mp4_output = render_mp4(Path(args.frames_dir), Path(args.mp4_output))
    if mp4_output is not None:
        print(f"Saved MP4 to {mp4_output}")


if __name__ == "__main__":
    main()
