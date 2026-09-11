#!/usr/bin/env python3
"""Develop selected Fuji RAFs and apply a restrained editorial finish."""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


SELECTIONS = [
    dict(raw="DSCF0004", name="01_window_repose", style="bw", aspect=3 / 2, center=(0.50, 0.50), exposure=-0.10, vignette=0.17),
    dict(raw="DSCF0017", name="02_fireplace_glance", style="color", aspect=4 / 5, center=(0.56, 0.48), exposure=0.55, vignette=0.18, dodge=(0.54, 0.34, 0.23, 0.26, 0.70)),
    dict(raw="DSCF0033", name="03_hearth_portrait", style="bw", aspect=1.0, center=(0.48, 0.52), exposure=0.35, vignette=0.22, dodge=(0.50, 0.35, 0.22, 0.24, 0.38)),
    dict(raw="DSCF0280", name="04_column_silhouette", style="bw", aspect=4 / 5, center=(0.44, 0.50), exposure=-0.20, vignette=0.18),
    dict(raw="DSCF0323", name="05_column_contrapposto", style="bw", aspect=4 / 5, center=(0.44, 0.50), exposure=-0.15, vignette=0.20),
    dict(raw="DSCF0340", name="06_profile_in_shadow", style="bw", aspect=4 / 5, center=(0.40, 0.48), exposure=-0.25, vignette=0.24),
    dict(raw="DSCF0354", name="07_brick_seat", style="color", aspect=4 / 5, center=(0.50, 0.50), exposure=0.00, vignette=0.18, dodge=(0.51, 0.31, 0.20, 0.23, 0.40)),
    dict(raw="DSCF0388", name="08_sunward", style="bw", aspect=4 / 5, center=(0.55, 0.48), exposure=-0.10, vignette=0.20),
    dict(raw="DSCF0440", name="09_terrace_profile", style="bw", aspect=4 / 5, center=(0.50, 0.48), exposure=-0.15, vignette=0.19),
    dict(raw="DSCF0496", name="10_over_shoulder", style="bw", aspect=4 / 5, center=(0.50, 0.47), exposure=0.00, vignette=0.20, dodge=(0.52, 0.30, 0.20, 0.22, 0.36)),
    dict(raw="DSCF0556", name="11_pink_stillness", style="color", aspect=4 / 5, center=(0.50, 0.47), exposure=-0.05, vignette=0.17, dodge=(0.50, 0.36, 0.24, 0.27, 1.60)),
    dict(raw="DSCF0563", name="12_pink_diagonal", style="color", aspect=4 / 5, center=(0.50, 0.48), exposure=-0.08, vignette=0.18, dodge=(0.51, 0.36, 0.24, 0.27, 1.50)),
    dict(raw="DSCF0716", name="13_garden_gaze", style="color", aspect=4 / 5, center=(0.50, 0.47), exposure=-0.02, vignette=0.19, dodge=(0.50, 0.34, 0.23, 0.26, 1.30)),
    dict(raw="DSCF0754", name="14_blue_window", style="color", aspect=3 / 2, center=(0.50, 0.50), exposure=1.20, vignette=0.24, dodge=(0.52, 0.33, 0.22, 0.24, 0.55)),
    dict(raw="DSCF0774", name="15_window_close", style="bw", aspect=1.0, center=(0.50, 0.47), exposure=1.00, vignette=0.25, dodge=(0.50, 0.34, 0.24, 0.25, 0.45)),
    dict(raw="DSCF0797", name="16_bed_geometry", style="bw", aspect=3 / 2, center=(0.50, 0.50), exposure=1.25, vignette=0.20),
    dict(raw="DSCF0811", name="17_bed_portrait", style="bw", aspect=3 / 2, center=(0.50, 0.51), exposure=0.65, vignette=0.18, dodge=(0.50, 0.70, 0.19, 0.18, 0.35)),
    dict(raw="DSCF0839", name="18_chair_intimacy", style="bw", aspect=4 / 5, center=(0.50, 0.49), exposure=0.22, vignette=0.21, dodge=(0.46, 0.29, 0.20, 0.22, 0.35)),
    dict(raw="DSCF0848", name="19_chair_direct", style="bw", aspect=4 / 5, center=(0.50, 0.48), exposure=0.15, vignette=0.20, dodge=(0.50, 0.28, 0.20, 0.22, 0.32)),
    dict(raw="DSCF0858", name="20_chair_release", style="bw", aspect=4 / 5, center=(0.49, 0.50), exposure=-0.12, vignette=0.17),
    dict(raw="DSCF0872", name="21_chair_recline", style="bw", aspect=4 / 5, center=(0.49, 0.50), exposure=-0.10, vignette=0.18),
    dict(raw="DSCF0875", name="22_kitchen_reverie", style="color", aspect=4 / 5, center=(0.47, 0.49), exposure=0.55, vignette=0.24, dodge=(0.48, 0.28, 0.25, 0.24, 0.30)),
    dict(raw="DSCF0882", name="23_kitchen_light", style="color", aspect=3 / 2, center=(0.50, 0.50), exposure=0.45, vignette=0.23, dodge=(0.51, 0.30, 0.23, 0.24, 0.28)),
    dict(raw="DSCF0883", name="24_kitchen_turn", style="color", aspect=3 / 2, center=(0.50, 0.50), exposure=0.42, vignette=0.23, dodge=(0.52, 0.30, 0.23, 0.24, 0.26)),
]


def srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.04045, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    return np.where(rgb <= 0.0031308, 12.92 * rgb, 1.055 * np.maximum(rgb, 0) ** (1 / 2.4) - 0.055)


def crop_to_aspect(image: np.ndarray, aspect: float, center: tuple[float, float]) -> np.ndarray:
    height, width = image.shape[:2]
    current = width / height
    if current > aspect:
        crop_h = height
        crop_w = int(round(crop_h * aspect))
    else:
        crop_w = width
        crop_h = int(round(crop_w / aspect))
    cx = int(round(center[0] * width))
    cy = int(round(center[1] * height))
    left = max(0, min(width - crop_w, cx - crop_w // 2))
    top = max(0, min(height - crop_h, cy - crop_h // 2))
    return image[top : top + crop_h, left : left + crop_w]


def aces_filmic(linear: np.ndarray) -> np.ndarray:
    a, b, c, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    return np.clip((linear * (a * linear + b)) / (linear * (c * linear + d) + e), 0, 1)


def global_tone(rgb: np.ndarray, exposure: float, monochrome: bool) -> np.ndarray:
    linear = srgb_to_linear(np.clip(rgb, 0, 1))
    lum = 0.2126 * linear[..., 0] + 0.7152 * linear[..., 1] + 0.0722 * linear[..., 2]
    p50, p90 = np.percentile(lum, [50, 90])
    target50 = 0.018 if monochrome else 0.022
    target90 = 0.42 if monochrome else 0.46
    gain50 = target50 / max(p50, 1e-5)
    gain90 = target90 / max(p90, 1e-5)
    auto_gain = float(np.clip(math.sqrt(gain50 * gain90), 0.45, 14.0))
    gain = float(np.clip(auto_gain * (2**exposure), 0.35, 40.0))
    linear = aces_filmic(linear * gain)
    return np.clip(linear_to_srgb(linear), 0, 1)


def local_dodge(
    rgb: np.ndarray,
    spec: tuple[float, float, float, float, float] | None,
    warm: bool = False,
) -> np.ndarray:
    if spec is None:
        return rgb
    cx, cy, rx, ry, stops = spec
    height, width = rgb.shape[:2]
    yy, xx = np.ogrid[:height, :width]
    distance = ((xx / width - cx) / rx) ** 2 + ((yy / height - cy) / ry) ** 2
    mask = np.exp(-2.2 * distance).astype(np.float32)[..., None]
    lifted = 1 - (1 - rgb) ** (2**stops)
    if warm:
        lifted = np.clip(lifted * np.array([1.07, 1.018, 0.925], np.float32), 0, 1)
    return rgb * (1 - mask) + lifted * mask


def color_grade(rgb: np.ndarray) -> np.ndarray:
    lum = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])[..., None]
    shadows = np.clip((0.58 - lum) / 0.58, 0, 1)
    highlights = np.clip((lum - 0.38) / 0.62, 0, 1)
    shadow_tint = np.array([0.94, 1.025, 1.075], np.float32)
    highlight_tint = np.array([1.075, 1.018, 0.925], np.float32)
    rgb = rgb * (1 + shadows * (shadow_tint - 1) + highlights * (highlight_tint - 1))

    hsv = cv2.cvtColor(np.clip(rgb, 0, 1).astype(np.float32), cv2.COLOR_RGB2HSV)
    hue, sat, val = cv2.split(hsv)
    greens = ((hue > 45) & (hue < 165)).astype(np.float32)
    hue = hue * (1 - 0.12 * greens) + 162 * (0.12 * greens)
    sat *= 1 - 0.24 * greens
    sat *= 0.92
    hsv = cv2.merge([hue, np.clip(sat, 0, 1), val])
    rgb = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

    skin = (
        (rgb[..., 0] > rgb[..., 1] * 1.025)
        & (rgb[..., 1] > rgb[..., 2] * 0.95)
        & (rgb[..., 0] > 0.16)
        & (rgb[..., 0] < 0.98)
    ).astype(np.float32)
    skin = cv2.GaussianBlur(skin, (0, 0), 5)[..., None]
    warm = rgb * np.array([1.025, 1.005, 0.975], np.float32)
    rgb = rgb * (1 - 0.18 * skin) + warm * (0.18 * skin)
    return np.clip(rgb, 0, 1)


def monochrome_grade(rgb: np.ndarray) -> np.ndarray:
    gray = 0.34 * rgb[..., 0] + 0.52 * rgb[..., 1] + 0.14 * rgb[..., 2]
    gray = np.clip((gray - 0.015) / 0.975, 0, 1)
    gray = 1 / (1 + np.exp(-5.35 * (gray - 0.50)))
    black, white = 1 / (1 + math.exp(2.675)), 1 / (1 + math.exp(-2.675))
    gray = np.clip((gray - black) / (white - black), 0, 1)
    return np.repeat(gray[..., None], 3, axis=2)


def finish_texture(rgb: np.ndarray, vignette: float, monochrome: bool, seed: int) -> np.ndarray:
    height, width = rgb.shape[:2]
    small = cv2.resize(rgb, (max(1, width // 2), max(1, height // 2)), interpolation=cv2.INTER_AREA)
    blur_small = cv2.GaussianBlur(small, (0, 0), 2.0)
    local = cv2.resize(small - blur_small, (width, height), interpolation=cv2.INTER_LINEAR)
    rgb = np.clip(rgb + local * (0.11 if monochrome else 0.075), 0, 1)

    yy, xx = np.ogrid[:height, :width]
    dx = (xx - width * 0.5) / (width * 0.70)
    dy = (yy - height * 0.48) / (height * 0.72)
    radial = np.clip((dx * dx + dy * dy - 0.18) / 0.82, 0, 1).astype(np.float32)[..., None]
    rgb *= 1 - vignette * radial

    soft = cv2.GaussianBlur(rgb, (0, 0), 0.72)
    rgb = np.clip(rgb * 1.24 - soft * 0.24, 0, 1)

    rng = np.random.default_rng(seed)
    noise = rng.normal(0, 0.010 if monochrome else 0.0055, (height, width, 1)).astype(np.float32)
    grain_weight = 0.45 + 0.85 * (1 - np.mean(rgb, axis=2, keepdims=True))
    return np.clip(rgb + noise * grain_weight, 0, 1)


def develop(raw_path: Path, tiff_path: Path) -> None:
    subprocess.run(
        [
            "dcraw_emu",
            "-w",
            "-H",
            "3",
            "-q",
            "4",
            "-o",
            "1",
            "-6",
            "-T",
            "-Z",
            str(tiff_path),
            str(raw_path),
        ],
        check=True,
    )


def copy_metadata(raw_path: Path, output_path: Path) -> None:
    subprocess.run(
        [
            "exiftool",
            "-overwrite_original",
            "-TagsFromFile",
            str(raw_path),
            "-EXIF:all",
            "-XMP:all",
            "-IPTC:all",
            "-Orientation#=1",
            "-ColorSpace#=1",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def process_one(item: dict, raw_dir: Path, output_dir: Path, temp_dir: Path, index: int) -> dict:
    raw_path = raw_dir / f"{item['raw']}.RAF"
    if not raw_path.exists():
        raise FileNotFoundError(raw_path)
    tiff_path = temp_dir / f"{item['raw']}.tif"
    output_path = output_dir / f"{item['name']}.jpg"
    develop(raw_path, tiff_path)
    source = cv2.imread(str(tiff_path), cv2.IMREAD_UNCHANGED)
    if source is None:
        raise RuntimeError(f"failed to read {tiff_path}")
    source = crop_to_aspect(source, item["aspect"], item["center"])
    rgb = cv2.cvtColor(source, cv2.COLOR_BGR2RGB).astype(np.float32) / 65535.0
    del source
    monochrome = item["style"] == "bw"
    rgb = global_tone(rgb, item["exposure"], monochrome)
    rgb = monochrome_grade(rgb) if monochrome else color_grade(rgb)
    rgb = local_dodge(rgb, item.get("dodge"), warm=not monochrome)
    rgb = finish_texture(rgb, item["vignette"], monochrome, seed=index * 7919)
    final = np.clip(rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(final, "RGB").save(
        output_path,
        format="JPEG",
        quality=96,
        subsampling=0,
        optimize=True,
        progressive=True,
        dpi=(300, 300),
    )
    copy_metadata(raw_path, output_path)
    tiff_path.unlink(missing_ok=True)
    return {
        "source": raw_path.name,
        "output": output_path.name,
        "style": item["style"],
        "pixels": [int(final.shape[1]), int(final.shape[0])],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--only", nargs="*", help="optional RAF stems for test runs")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    selected = [x for x in SELECTIONS if not args.only or x["raw"] in set(args.only)]
    manifest = []
    with tempfile.TemporaryDirectory(prefix="photo_finish_", dir=args.work_dir) as temp:
        temp_dir = Path(temp)
        for index, item in enumerate(selected, start=1):
            print(f"[{index}/{len(selected)}] {item['raw']} -> {item['name']}.jpg", flush=True)
            manifest.append(process_one(item, args.raw_dir, args.output_dir, temp_dir, index))
    manifest_path = args.work_dir / "final_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(manifest)} final JPGs to {args.output_dir}")


if __name__ == "__main__":
    main()
