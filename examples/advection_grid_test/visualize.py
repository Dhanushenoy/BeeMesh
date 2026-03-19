"""
Visualize the final field for the coupled 2D advection example.
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
DEFAULT_OUTPUT = Path(__file__).resolve().parent / "advection_final.png"
DEFAULT_GIF = Path(__file__).resolve().parent / "advection_evolution.gif"
DEFAULT_MP4 = Path(__file__).resolve().parent / "advection_evolution.mp4"
DEFAULT_VMIN = 0.0
DEFAULT_VMAX = 0.8


def render_field(
    field: np.ndarray,
    output_path: Path,
    step: Optional[int] = None,
    x_parts=None,
    y_parts=None,
    partition_overlays=None,
    step_history=None,
    vmin: float = DEFAULT_VMIN,
    vmax: float = DEFAULT_VMAX,
    surface_3d: bool = False,
):
    try:
        import matplotlib.pyplot as plt
        from matplotlib import cm
        from matplotlib import rcParams
    except ImportError:
        print("matplotlib not installed. Final field shape:", field.shape)
        return output_path

    rcParams["font.family"] = "serif"
    rcParams["mathtext.fontset"] = "cm"

    fig = plt.figure(figsize=(18, 8))
    gs = fig.add_gridspec(
        2,
        3,
        width_ratios=[1.65, 1.20, 0.95],
        height_ratios=[1.0, 0.06],
        wspace=0.28,
        hspace=0.08,
    )
    ax = fig.add_subplot(gs[0, 0])
    ax3d = fig.add_subplot(gs[0, 1], projection="3d")
    ax_ts = fig.add_subplot(gs[0, 2])
    cax = fig.add_subplot(gs[1, 1])
    fig.patch.set_facecolor("black")
    ax.set_facecolor("black")
    ax3d.set_facecolor("black")
    ax_ts.set_facecolor("black")
    image = ax.imshow(field, origin="lower", cmap="berlin", vmin=vmin, vmax=vmax)
    y_coords = np.arange(field.shape[1])
    x_coords = np.arange(field.shape[0])
    yy, xx = np.meshgrid(y_coords, x_coords)
    surface = ax3d.plot_surface(
        yy,
        xx,
        field,
        cmap=cm.get_cmap("berlin"),
        vmin=vmin,
        vmax=vmax,
        linewidth=0,
        antialiased=False,
        shade=True,
    )
    ax3d.view_init(elev=34, azim=-123)
    ax3d.set_zlim(vmin, vmax)
    ax3d.set_box_aspect((field.shape[1], field.shape[0], 36))
    ax3d.set_zlabel("u")
    ax3d.zaxis.label.set_color("white")
    ax3d.tick_params(colors="white")
    ax3d.xaxis.set_pane_color((0.0, 0.0, 0.0, 1.0))
    ax3d.yaxis.set_pane_color((0.0, 0.0, 0.0, 1.0))
    ax3d.zaxis.set_pane_color((0.0, 0.0, 0.0, 1.0))
    title = "BeeMesh 2D Advection"
    if step is not None:
        title += f"\nStep {step}"
    ax.set_title(title, fontsize=12, fontweight="semibold")
    ax.set_xlabel("Y Grid Index")
    ax.set_ylabel("X Grid Index")
    ax.title.set_color("white")
    ax.xaxis.label.set_color("white")
    ax.yaxis.label.set_color("white")
    ax.tick_params(colors="white")
    ax3d.set_title("BeeMesh 3D Surface", fontsize=12, fontweight="semibold", color="white")
    ax3d.set_xlabel("Y Grid Index")
    ax3d.set_ylabel("X Grid Index")
    ax3d.xaxis.label.set_color("white")
    ax3d.yaxis.label.set_color("white")

    x_boundaries = [boundary[0] for boundary in (x_parts or [])[1:]]
    y_boundaries = [boundary[0] for boundary in (y_parts or [])[1:]]

    z_line = vmax * 1.01
    for x0 in x_boundaries:
        ax.axhline(
            x0 - 0.5,
            color="white",
            linewidth=1.0,
            alpha=0.85,
            linestyle=(0, (2, 2)),
        )
        ax3d.plot(
            [0, field.shape[1] - 1],
            [x0 - 0.5, x0 - 0.5],
            [z_line, z_line],
            color="white",
            linewidth=1.0,
            alpha=0.8,
            linestyle=":",
        )

    for index, overlay in enumerate(partition_overlays or []):
        x0 = float(overlay.get("x0", 0))
        x1 = float(overlay.get("x1", 0))
        y0 = float(overlay.get("y0", 0))
        y1 = float(overlay.get("y1", 0))
        shade = "#b0b0b0" if index % 2 == 0 else "#6e6e6e"
        ax.axhspan(
            x0 - 0.5,
            x1 - 0.5,
            xmin=max(0.0, y0 / max(field.shape[1], 1)),
            xmax=min(1.0, y1 / max(field.shape[1], 1)),
            color=shade,
            alpha=0.055,
            linewidth=0,
            zorder=2.2,
        )
    for y0 in y_boundaries:
        ax.axvline(
            y0 - 0.5,
            color="white",
            linewidth=1.0,
            alpha=0.85,
            linestyle=(0, (2, 2)),
        )
        ax3d.plot(
            [y0 - 0.5, y0 - 0.5],
            [0, field.shape[0] - 1],
            [z_line, z_line],
            color="white",
            linewidth=1.0,
            alpha=0.8,
            linestyle=":",
        )

    if x_boundaries or y_boundaries:
        ax.text(
            0.02,
            0.09,
            "Gaussian pulse advected upward across distributed Bee partitions",
            transform=ax.transAxes,
            fontsize=10.0,
            color="#ffffff",
            ha="left",
            va="bottom",
            bbox={"facecolor": "black", "alpha": 0.28, "pad": 3, "edgecolor": "none"},
        )
        ax.text(
            0.02,
            0.04,
            "Dotted lines show bee tile partitions",
            transform=ax.transAxes,
            fontsize=10.5,
            color="#ffffff",
            ha="left",
            va="bottom",
            bbox={"facecolor": "black", "alpha": 0.34, "pad": 3, "edgecolor": "none"},
        )

    for overlay in partition_overlays or []:
        x0 = float(overlay.get("x0", 0))
        x1 = float(overlay.get("x1", 0))
        y0 = float(overlay.get("y0", 0))
        y1 = float(overlay.get("y1", 0))
        hostname = overlay.get("hostname") or overlay.get("worker_id") or "unassigned"
        display_name = hostname[:-4] if hostname.endswith("-bee") else hostname
        cpu = overlay.get("cpu_cores")
        ram = overlay.get("ram_gb")
        arch = overlay.get("architecture")
        specs = []
        if cpu is not None:
            specs.append(f"{cpu} CPU")
        if ram is not None:
            try:
                specs.append(f"{float(ram):.0f} GB")
            except (TypeError, ValueError):
                specs.append(f"{ram} GB")
        if arch:
            specs.append(str(arch))
        ax.text(
            y0 + 1.5,
            x1 - 1.5,
            display_name,
            fontsize=12.2,
            color="white",
            alpha=0.72,
            ha="left",
            va="top",
            rotation=0,
            bbox={"facecolor": "black", "alpha": 0.14, "pad": 2.0, "edgecolor": "none"},
        )
        if specs:
            ax.text(
                y1 - 1.5,
                x1 - 1.5,
                " | ".join(specs),
                fontsize=7.8,
                color="white",
                alpha=0.68,
                ha="right",
                va="top",
                rotation=0,
                bbox={"facecolor": "black", "alpha": 0.10, "pad": 1.6, "edgecolor": "none"},
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
            ax_ts.axvline(step, color="#ffffff", linewidth=1.2, alpha=0.8, linestyle=(0, (2, 2)))
            current = next((entry for entry in step_history or [] if entry.get("step") == step), None)
            if current is not None:
                current_y = 1000.0 * float(current.get("network_overhead_s", 0.0) or 0.0)
                ax_ts.scatter([step], [current_y], s=26, color="#ffffff", zorder=5)
        ax_ts.set_title("Per-step link timing", fontsize=11, fontweight="semibold")
        ax_ts.set_xlabel("Step")
        ax_ts.set_ylabel("Milliseconds")
        ax_ts.set_xlim(0, max(steps))
        ax_ts.title.set_color("white")
        ax_ts.xaxis.label.set_color("white")
        ax_ts.yaxis.label.set_color("white")
        ax_ts.tick_params(colors="white")
        ax_ts.grid(alpha=0.18, linestyle=":")
        legend = ax_ts.legend(loc="upper right", fontsize=7.8, frameon=False)
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

    for spine in ax.spines.values():
        spine.set_color("white")
    for spine in ax_ts.spines.values():
        spine.set_color("white")

    cbar = fig.colorbar(surface if surface_3d else image, cax=cax, orientation="horizontal")
    cbar.set_label("u", color="white")
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
    vmin: float,
    vmax: float,
    surface_3d: bool,
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
            vmin=vmin,
            vmax=vmax,
            surface_3d=surface_3d,
        )

    return len(snapshots)


def main():
    parser = argparse.ArgumentParser(description="Visualize BeeMesh advection output.")
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
    parser.add_argument("--vmin", type=float, default=DEFAULT_VMIN)
    parser.add_argument("--vmax", type=float, default=DEFAULT_VMAX)
    parser.add_argument("--surface-3d", action="store_true")
    args = parser.parse_args()

    rebuilt = rebuild_frames(
        Path(args.frames_file),
        Path(args.partitions_file),
        Path(args.history_file),
        Path(args.frames_dir),
        args.vmin,
        args.vmax,
        args.surface_3d,
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
        vmin=args.vmin,
        vmax=args.vmax,
        surface_3d=args.surface_3d,
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
