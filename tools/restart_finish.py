#!/usr/bin/env python3
"""Develop the restart photo set from full-resolution 16-bit RAW TIFF renders.

This is deliberately configuration-driven: each photograph has its own crop,
tone curve, local dodge/burn, and restrained finish.  No generative edits or
geometry changes are performed.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageCms


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "work" / "restart" / "inspection_tiff"
BEFORE_DIR = ROOT / "work" / "restart" / "before_crops"
DRAFT_DIR = ROOT / "work" / "restart" / "drafts_v1"


@dataclass(frozen=True)
class LocalTone:
    center: tuple[float, float]
    radius: tuple[float, float]
    ev: float


@dataclass(frozen=True)
class Recipe:
    crop: tuple[int, int, int, int]
    mode: str
    curve: tuple[tuple[float, float], ...]
    locals: tuple[LocalTone, ...] = field(default_factory=tuple)
    vignette: float = 0.0
    clarity: float = 0.10
    sharpen: float = 0.28
    grain: float = 0.0
    warm_highlights: float = 0.0
    cool_shadows: float = 0.0
    green_saturation: float = 1.0
    overall_saturation: float = 1.0


RECIPES: dict[str, Recipe] = {
    "0017": Recipe(
        crop=(1750, 0, 3336, 4170),
        mode="bw",
        curve=((0, .018), (.06, .055), (.22, .19), (.50, .49), (.78, .80), (1, .965)),
        locals=(LocalTone((.38, .29), (.25, .27), .10),),
        vignette=.09,
        clarity=.08,
        sharpen=.22,
        grain=.0025,
    ),
    "0323": Recipe(
        crop=(1500, 0, 3336, 4170),
        mode="bw",
        curve=((0, .012), (.05, .045), (.20, .17), (.48, .50), (.78, .83), (1, .975)),
        locals=(LocalTone((.48, .45), (.34, .47), .08),),
        vignette=.05,
        clarity=.13,
        sharpen=.24,
        grain=.0018,
    ),
    "0496": Recipe(
        # Keep the supporting hand in-frame and let the body sit off-center.
        crop=(1050, 0, 3336, 4170),
        mode="bw",
        curve=((0, .018), (.06, .06), (.22, .20), (.50, .52), (.80, .84), (1, .97)),
        locals=(LocalTone((.59, .23), (.24, .24), .12),),
        vignette=.08,
        clarity=.08,
        sharpen=.26,
        grain=.0015,
    ),
    "0552": Recipe(
        crop=(500, 0, 5212, 4170),
        mode="color",
        curve=((0, .022), (.06, .070), (.24, .270), (.50, .545), (.78, .805), (1, .960)),
        locals=(
            LocalTone((.49, .32), (.19, .25), .20),
            LocalTone((.50, .50), (.54, .64), .045),
        ),
        vignette=.055,
        clarity=.06,
        sharpen=.23,
        warm_highlights=.045,
        cool_shadows=.010,
        green_saturation=.76,
        overall_saturation=.92,
    ),
    "0754": Recipe(
        crop=(700, 0, 5212, 4170),
        mode="bw",
        curve=((0, .022), (.06, .065), (.24, .225), (.50, .51), (.80, .845), (1, .97)),
        locals=(LocalTone((.56, .24), (.19, .24), .08),),
        vignette=.075,
        clarity=.065,
        sharpen=.20,
        grain=.0022,
    ),
    "0779": Recipe(
        crop=(1200, 0, 3336, 4170),
        mode="bw",
        curve=((0, .020), (.06, .06), (.23, .205), (.50, .50), (.80, .84), (1, .97)),
        locals=(LocalTone((.49, .35), (.30, .31), .08),),
        vignette=.105,
        clarity=.045,
        sharpen=.19,
        grain=.0026,
    ),
    "0823": Recipe(
        crop=(1038, 0, 4170, 4170),
        mode="bw",
        curve=((0, .022), (.07, .065), (.25, .225), (.50, .51), (.80, .84), (1, .965)),
        locals=(LocalTone((.50, .48), (.27, .50), .05),),
        vignette=.055,
        clarity=.055,
        sharpen=.16,
        grain=.0034,
    ),
    "0839": Recipe(
        crop=(1400, 0, 3336, 4170),
        mode="bw",
        curve=((0, .022), (.07, .065), (.25, .225), (.50, .51), (.80, .84), (1, .965)),
        locals=(LocalTone((.37, .26), (.24, .25), .08),),
        vignette=.095,
        clarity=.045,
        sharpen=.18,
        grain=.0030,
    ),
    "0875": Recipe(
        crop=(900, 0, 3336, 4170),
        mode="color",
        curve=((0, .020), (.05, .075), (.20, .250), (.48, .540), (.76, .800), (1, .955)),
        locals=(LocalTone((.48, .27), (.31, .31), .20),),
        vignette=.070,
        clarity=.09,
        sharpen=.22,
        warm_highlights=.060,
        cool_shadows=.035,
        green_saturation=.78,
        overall_saturation=.88,
    ),
}


def srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def read_rgb16(path: Path) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise FileNotFoundError(path)
    if bgr.dtype == np.uint16:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 65535.0
    else:
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    return np.clip(rgb, 0.0, 1.0)


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * .2126 + rgb[..., 1] * .7152 + rgb[..., 2] * .0722


def apply_luma_curve(rgb: np.ndarray, points: tuple[tuple[float, float], ...]) -> np.ndarray:
    old = luminance(rgb)
    xp = np.array([p[0] for p in points], np.float32)
    fp = np.array([p[1] for p in points], np.float32)
    new = np.interp(old, xp, fp).astype(np.float32)
    ratio = np.clip(new / np.maximum(old, 1e-4), 0.0, 3.0)
    return np.clip(rgb * ratio[..., None], 0.0, 1.0)


def ellipse_mask(h: int, w: int, tone: LocalTone) -> np.ndarray:
    yy, xx = np.ogrid[:h, :w]
    cx, cy = tone.center[0] * w, tone.center[1] * h
    rx, ry = max(1.0, tone.radius[0] * w), max(1.0, tone.radius[1] * h)
    d2 = ((xx - cx) / rx) ** 2 + ((yy - cy) / ry) ** 2
    return np.exp(-2.0 * d2).astype(np.float32)


def local_dodge_burn(rgb: np.ndarray, tones: tuple[LocalTone, ...]) -> np.ndarray:
    h, w = rgb.shape[:2]
    out = rgb
    for tone in tones:
        mask = ellipse_mask(h, w, tone)
        multiplier = np.exp2(tone.ev * mask).astype(np.float32)
        out = np.clip(out * multiplier[..., None], 0.0, 1.0)
    return out


def soft_shadow_lift(
    rgb: np.ndarray,
    tone: LocalTone,
    amount: float,
    pivot: float = .38,
) -> np.ndarray:
    """Gently add exposure only to deep local shadows.

    Multiplicative dodging cannot reveal values close to black.  This restrained
    additive lift is reserved for the face in the hard-window-light frame.
    """
    y = luminance(rgb)
    shadow_weight = np.clip((pivot - y) / pivot, 0.0, 1.0) ** 1.45
    mask = ellipse_mask(*rgb.shape[:2], tone)
    lift = amount * mask * shadow_weight
    neutral_warm = np.array((1.00, .94, .86), dtype=np.float32)
    return np.clip(rgb + lift[..., None] * neutral_warm, 0.0, 1.0)


def apply_vignette(rgb: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return rgb
    h, w = rgb.shape[:2]
    yy = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    xx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    radius = np.sqrt(xx * xx + yy * yy)
    edge = np.clip((radius - .28) / 1.05, 0.0, 1.0) ** 1.7
    return np.clip(rgb * (1.0 - amount * edge[..., None]), 0.0, 1.0)


def suppress_chroma_noise(rgb: np.ndarray, sigma: float = .8) -> np.ndarray:
    luma = luminance(rgb)
    blurred = cv2.GaussianBlur(rgb, (0, 0), sigmaX=sigma, sigmaY=sigma)
    blurred_luma = luminance(blurred)
    chroma = blurred - blurred_luma[..., None]
    return np.clip(luma[..., None] + chroma, 0.0, 1.0)


def reduce_green_saturation(rgb: np.ndarray, green_factor: float, overall: float) -> np.ndarray:
    hsv = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0]
    green = np.clip(1.0 - np.abs(hue - 110.0) / 80.0, 0.0, 1.0)
    hsv[..., 1] *= overall * (1.0 - green * (1.0 - green_factor))
    hsv[..., 1] = np.clip(hsv[..., 1], 0.0, 1.0)
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)


def split_tone(rgb: np.ndarray, warm: float, cool: float) -> np.ndarray:
    if warm == 0 and cool == 0:
        return rgb
    y = luminance(rgb)
    highlights = np.clip((y - .38) / .62, 0.0, 1.0) ** 1.35
    shadows = np.clip((.58 - y) / .58, 0.0, 1.0) ** 1.35
    gains = np.ones_like(rgb)
    gains[..., 0] += warm * highlights - cool * .38 * shadows
    gains[..., 1] += warm * .18 * highlights + cool * .08 * shadows
    gains[..., 2] -= warm * .55 * highlights
    gains[..., 2] += cool * shadows
    return np.clip(rgb * gains, 0.0, 1.0)


def monochrome(rgb: np.ndarray) -> np.ndarray:
    # A slightly red-sensitive channel mix keeps skin luminous without flattening hair.
    gray = rgb[..., 0] * .31 + rgb[..., 1] * .57 + rgb[..., 2] * .12
    return np.repeat(np.clip(gray, 0.0, 1.0)[..., None], 3, axis=2)


def local_clarity_and_sharpen(rgb: np.ndarray, clarity: float, sharpen: float) -> np.ndarray:
    if clarity:
        broad = cv2.GaussianBlur(rgb, (0, 0), sigmaX=16.0, sigmaY=16.0)
        rgb = np.clip(rgb + clarity * (rgb - broad), 0.0, 1.0)
    if sharpen:
        fine = cv2.GaussianBlur(rgb, (0, 0), sigmaX=1.05, sigmaY=1.05)
        rgb = np.clip(rgb + sharpen * (rgb - fine), 0.0, 1.0)
    return rgb


def add_grain(rgb: np.ndarray, amount: float, seed: int) -> np.ndarray:
    if amount <= 0:
        return rgb
    rng = np.random.default_rng(seed)
    noise = rng.normal(0.0, amount, rgb.shape[:2]).astype(np.float32)
    y = luminance(rgb)
    envelope = np.sqrt(np.clip(1.0 - np.abs(y - .5) * 1.55, .18, 1.0))
    return np.clip(rgb + (noise * envelope)[..., None], 0.0, 1.0)


def repair_0839_outlet(rgb: np.ndarray) -> np.ndarray:
    """Content-aware fill the clipped outlet while preserving the wall falloff."""
    mask = np.zeros(rgb.shape[:2], dtype=np.uint8)
    cv2.rectangle(mask, (240, 3690), (670, rgb.shape[0] - 1), 255, thickness=-1)
    # The plate is close to the lower edge; a generous Telea radius propagates
    # the clean wall from the top and both sides without a hard cloned boundary.
    rgb8 = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    repaired = cv2.inpaint(rgb8, mask, 24.0, cv2.INPAINT_TELEA)
    return repaired.astype(np.float32) / 255.0


def save_jpeg(rgb: np.ndarray, path: Path, quality: int = 96) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    array = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    image = Image.fromarray(array, "RGB")
    image.save(
        path,
        format="JPEG",
        quality=quality,
        subsampling=0,
        optimize=True,
        icc_profile=srgb_profile_bytes(),
        exif=Image.Exif(),
    )


def develop(number: str, recipe: Recipe) -> None:
    rgb = read_rgb16(SOURCE_DIR / f"DSCF{number}.tiff")
    x, y, w, h = recipe.crop
    rgb = rgb[y:y + h, x:x + w].copy()

    # Preserve an unstyled, exposure-normalized crop as the authoritative before.
    save_jpeg(rgb, BEFORE_DIR / f"DSCF{number}_before.jpg", quality=95)

    rgb = suppress_chroma_noise(rgb, sigma=.72 if recipe.mode == "color" else .58)
    rgb = apply_luma_curve(rgb, recipe.curve)
    rgb = local_dodge_burn(rgb, recipe.locals)
    if number == "0875":
        rgb = soft_shadow_lift(
            rgb,
            LocalTone((.44, .18), (.25, .22), 0.0),
            amount=.055,
        )
    rgb = apply_vignette(rgb, recipe.vignette)

    if recipe.mode == "bw":
        rgb = monochrome(rgb)
    else:
        rgb = reduce_green_saturation(rgb, recipe.green_saturation, recipe.overall_saturation)
        rgb = split_tone(rgb, recipe.warm_highlights, recipe.cool_shadows)

    if number == "0839":
        rgb = repair_0839_outlet(rgb)

    rgb = local_clarity_and_sharpen(rgb, recipe.clarity, recipe.sharpen)
    rgb = add_grain(rgb, recipe.grain, seed=int(number))
    save_jpeg(rgb, DRAFT_DIR / f"DSCF{number}_edit_v1.jpg")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("numbers", nargs="*", help="four-digit frame numbers")
    args = parser.parse_args()
    numbers = args.numbers or list(RECIPES)
    for number in numbers:
        develop(number, RECIPES[number])
        print(f"developed DSCF{number}")


if __name__ == "__main__":
    main()
