#!/usr/bin/env python3
"""Reference-led development of the third-pass photo selection.

The input is a fixed-exposure, linear-light, 16-bit TIFF decoded from each RAF.
Every frame has its own crop and local exposure masks, followed by one of the
six visual families extracted from the supplied references.  The script never
changes identity, body geometry, clothing, or scene structure.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageCms
from scipy.interpolate import PchipInterpolator


ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / "work" / "reference_restart"
BASE_DIR = WORK / "linear_tiff" / "base"
H2_DIR = WORK / "linear_tiff" / "h2"
H3_DIR = WORK / "linear_tiff" / "h3"
SOURCE_JPG_DIR = WORK / "fullres_inspection_jpg"
BEFORE_DIR = WORK / "before_crops"
LOOK_DIR = WORK / "looks_v1"
METRICS_PATH = WORK / "looks_v1_metrics.json"


@dataclass(frozen=True)
class Target:
    p01: float
    p25: float
    p50: float
    p75: float
    p99: float
    minimum: float
    maximum: float


@dataclass(frozen=True)
class Look:
    name: str
    mode: str
    target: Target
    grain: float
    clarity: float
    sharpen: float
    grade: str = "neutral"
    vignette: float = 0.0


@dataclass(frozen=True)
class Recipe:
    crop: tuple[int, int, int, int]  # left, top, right, bottom
    exposure_ev: float
    white_point: float
    chroma_sigma: float
    use_h2: bool
    face: tuple[float, float, float, float] | None
    looks: tuple[Look, Look]


def target(values: tuple[float, float, float, float, float], minimum: float, maximum: float) -> Target:
    return Target(*values, minimum, maximum)


RECIPES: dict[str, Recipe] = {
    "0017": Recipe(
        crop=(1450, 150, 4650, 4150), exposure_ev=4.05, white_point=4.3,
        chroma_sigma=.55, use_h2=False, face=(.482, .267, .205, .175),
        looks=(
            Look("A_gritty_documentary_bw", "bw", target((.008, .18, .37, .70, .89), .002, .965), .0150, .075, .18, vignette=.045),
            Look("B_refined_lowkey_bw", "bw", target((.022, .055, .17, .32, .95), .009, .978), .0065, .050, .16, vignette=.075),
        ),
    ),
    "0323": Recipe(
        crop=(1550, 0, 4330, 4170), exposure_ev=2.05, white_point=3.8,
        chroma_sigma=.45, use_h2=False, face=None,
        looks=(
            Look("A_architectural_silhouette_bw", "bw", target((.066, .105, .145, .39, .975), .052, .986), .0050, .050, .16),
            Look("B_lifted_silhouette_bw", "bw", target((.083, .125, .175, .43, .972), .068, .985), .0045, .045, .15),
        ),
    ),
    "0352": Recipe(
        crop=(1300, 0, 5470, 4170), exposure_ev=.75, white_point=3.9,
        chroma_sigma=.75, use_h2=True, face=(.554, .179, .145, .145),
        looks=(
            Look("A_faded_warm_motion", "color", target((.055, .33, .515, .65, .855), .032, .935), .0095, .020, .10, grade="faded", vignette=.025),
            Look("B_gritty_motion_bw", "bw", target((.009, .18, .37, .69, .89), .002, .965), .0130, .045, .13, vignette=.035),
        ),
    ),
    "0496": Recipe(
        crop=(750, 0, 4920, 4170), exposure_ev=.55, white_point=4.0,
        chroma_sigma=.65, use_h2=True, face=(.550, .213, .160, .165),
        looks=(
            Look("A_refined_lowkey_bw", "bw", target((.022, .052, .17, .31, .95), .008, .978), .0060, .045, .15, vignette=.075),
            Look("B_faded_warm_portrait", "color", target((.060, .33, .505, .65, .855), .038, .935), .0080, .020, .10, grade="faded", vignette=.035),
        ),
    ),
    "0560": Recipe(
        crop=(0, 0, 5212, 4170), exposure_ev=.62, white_point=4.0,
        chroma_sigma=.82, use_h2=True, face=(.580, .457, .150, .195),
        looks=(
            Look("A_faded_warm_film", "color", target((.060, .34, .525, .66, .86), .038, .938), .0090, .018, .10, grade="faded", vignette=.025),
            Look("B_pale_pastel_film", "color", target((.105, .41, .60, .73, .925), .075, .970), .0075, .012, .08, grade="pale", vignette=.018),
        ),
    ),
    "0754": Recipe(
        crop=(1500, 0, 5670, 4170), exposure_ev=4.65, white_point=4.5,
        chroma_sigma=.72, use_h2=False, face=(.508, .236, .155, .170),
        looks=(
            Look("A_refined_window_lowkey_bw", "bw", target((.022, .052, .17, .32, .95), .008, .979), .0060, .040, .14, vignette=.065),
            Look("B_open_window_bw", "bw", target((.016, .10, .25, .48, .935), .005, .978), .0060, .035, .13, vignette=.035),
        ),
    ),
    "0773": Recipe(
        crop=(550, 0, 4720, 4170), exposure_ev=4.65, white_point=4.5,
        chroma_sigma=.78, use_h2=False, face=(.539, .310, .175, .185),
        looks=(
            Look("A_intimate_gritty_bw", "bw", target((.009, .18, .37, .69, .89), .002, .965), .0100, .045, .13, vignette=.060),
            Look("B_intimate_refined_bw", "bw", target((.023, .060, .18, .34, .95), .009, .978), .0055, .035, .12, vignette=.075),
        ),
    ),
    "0823": Recipe(
        crop=(1038, 0, 5208, 4170), exposure_ev=4.15, white_point=4.2,
        chroma_sigma=1.05, use_h2=False, face=None,
        looks=(
            Look("A_graphic_highkey_bw", "bw", target((.055, .24, .60, .86, .94), .025, .972), .0040, .025, .11),
            Look("B_sculptural_bw", "bw", target((.028, .14, .41, .73, .95), .010, .978), .0045, .035, .12, vignette=.018),
        ),
    ),
    "0843": Recipe(
        crop=(500, 0, 4670, 4170), exposure_ev=2.25, white_point=4.2,
        chroma_sigma=1.05, use_h2=False, face=(.566, .288, .175, .185),
        looks=(
            Look("A_intimate_gritty_bw", "bw", target((.011, .19, .37, .68, .90), .003, .968), .0080, .035, .12, vignette=.060),
            Look("B_refined_chair_bw", "bw", target((.022, .060, .18, .34, .95), .008, .978), .0045, .030, .11, vignette=.075),
        ),
    ),
    "0875": Recipe(
        crop=(1800, 0, 4146, 4170), exposure_ev=2.55, white_point=5.0,
        chroma_sigma=1.10, use_h2=True, face=(.365, .205, .245, .190),
        looks=(
            Look("A_cinematic_amber_teal", "color", target((.105, .23, .31, .48, .90), .075, .965), .0055, .030, .12, grade="cinema", vignette=.018),
            Look("B_neutral_hardsun_bw", "bw", target((.065, .105, .17, .41, .975), .045, .986), .0045, .045, .13),
        ),
    ),
}


def srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def read_linear_crop(path: Path, crop: tuple[int, int, int, int]) -> np.ndarray:
    bgr = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if bgr is None:
        raise FileNotFoundError(path)
    left, top, right, bottom = crop
    bgr = bgr[top:bottom, left:right]
    scale = 65535.0 if bgr.dtype == np.uint16 else 255.0
    return np.ascontiguousarray(bgr[..., ::-1], dtype=np.float32) / scale


def luminance(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * .2126 + rgb[..., 1] * .7152 + rgb[..., 2] * .0722


def smoothstep(edge0: float, edge1: float, values: np.ndarray) -> np.ndarray:
    t = np.clip((values - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def ellipse_mask(shape: tuple[int, int], spec: tuple[float, float, float, float], feather: float = 2.0) -> np.ndarray:
    h, w = shape
    cx, cy, rx, ry = spec
    yy, xx = np.ogrid[:h, :w]
    d2 = ((xx / w - cx) / max(rx, 1e-4)) ** 2 + ((yy / h - cy) / max(ry, 1e-4)) ** 2
    return np.exp(-feather * d2).astype(np.float32)


def polygon_mask(shape: tuple[int, int], points: list[tuple[float, float]], feather_px: float) -> np.ndarray:
    h, w = shape
    pts = np.array([[(int(x * w), int(y * h)) for x, y in points]], np.int32)
    mask = np.zeros((h, w), np.float32)
    cv2.fillPoly(mask, pts, 1.0)
    if feather_px:
        mask = cv2.GaussianBlur(mask, (0, 0), feather_px)
    return np.clip(mask, 0.0, 1.0)


def gradient_y(shape: tuple[int, int], start: float, end: float, invert: bool = False) -> np.ndarray:
    h, w = shape
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    result = smoothstep(start, end, y)
    if invert:
        result = 1.0 - result
    return np.broadcast_to(result, (h, w)).copy()


def gradient_x(shape: tuple[int, int], start: float, end: float, invert: bool = False) -> np.ndarray:
    h, w = shape
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    result = smoothstep(start, end, x)
    if invert:
        result = 1.0 - result
    return np.broadcast_to(result, (h, w)).copy()


def apply_local_ev(linear: np.ndarray, mask: np.ndarray, ev: float, shadow_pivot: float | None = None) -> np.ndarray:
    weight = mask
    if shadow_pivot is not None:
        y = luminance(linear)
        weight = weight * np.clip((shadow_pivot - y) / max(shadow_pivot, 1e-5), 0.0, 1.0) ** 1.25
    gain = np.exp2(ev * weight).astype(np.float32)
    return linear * gain[..., None]


def merge_highlights(base: np.ndarray, companion: np.ndarray) -> np.ndarray:
    """Normalize an H2 render to H0, then use it only near H0 clipping."""
    base_y = luminance(base)
    comp_y = luminance(companion)
    valid = (base_y > .025) & (base_y < .45) & (comp_y > .008)
    scale = float(np.median(base_y[valid] / comp_y[valid])) if np.any(valid) else 1.0
    recovered = companion * scale
    peak = np.max(base, axis=2)
    mask = smoothstep(.68, .985, peak)
    mask = cv2.GaussianBlur(mask, (0, 0), 3.2)
    return base * (1.0 - mask[..., None]) + recovered * mask[..., None]


def source_adjustments(number: str, linear: np.ndarray, recipe: Recipe) -> np.ndarray:
    shape = linear.shape[:2]
    face = ellipse_mask(shape, recipe.face) if recipe.face else None

    if number == "0017":
        linear = apply_local_ev(linear, face, .22)
        # Keep the documentary lamp, but stop its white orb from stealing the frame.
        linear = apply_local_ev(linear, ellipse_mask(shape, (.035, .29, .13, .22)), -.85)
        linear = apply_local_ev(linear, ellipse_mask(shape, (.56, .49, .25, .20)), .12)
    elif number == "0323":
        linear = apply_local_ev(linear, gradient_y(shape, .72, 1.0), .52, shadow_pivot=.10)
    elif number == "0352":
        linear = apply_local_ev(linear, face, .30, shadow_pivot=.22)
    elif number == "0496":
        linear = apply_local_ev(linear, face, .34, shadow_pivot=.30)
        subject = polygon_mask(shape, [(.34, .03), (.69, .02), (.78, .97), (.43, 1.0), (.30, .69), (.01, .69), (.01, .52)], 120)
        linear = apply_local_ev(linear, 1.0 - subject, -.42)
    elif number == "0560":
        linear = apply_local_ev(linear, face, 1.05, shadow_pivot=.25)
        torso = ellipse_mask(shape, (.57, .61, .28, .52))
        linear = apply_local_ev(linear, torso, .18, shadow_pivot=.30)
    elif number == "0754":
        linear = apply_local_ev(linear, face, .34, shadow_pivot=.16)
        linear = apply_local_ev(linear, gradient_x(shape, .66, 1.0), -.38)
    elif number == "0773":
        linear = apply_local_ev(linear, face, .24, shadow_pivot=.18)
        linear = apply_local_ev(linear, gradient_y(shape, .73, 1.0), -.16)
    elif number == "0823":
        wall = gradient_y(shape, .36, .16, invert=True)
        # The intentionally dark headboard remains the graphic anchor.
        board = polygon_mask(shape, [(0, .28), (1, .28), (1, .79), (0, .79)], 50)
        limbs = polygon_mask(shape, [(.43, .04), (.57, .04), (.61, .78), (.39, .78)], 75)
        linear = apply_local_ev(linear, wall, .42)
        linear = apply_local_ev(linear, board, -.24)
        linear = apply_local_ev(linear, limbs, .20, shadow_pivot=.20)
    elif number == "0843":
        linear = apply_local_ev(linear, face, .32, shadow_pivot=.22)
        subject = ellipse_mask(shape, (.58, .54, .39, .62), feather=1.5)
        linear = apply_local_ev(linear, 1.0 - subject, -.34)
    elif number == "0875":
        # Recover the unlit half of the face without flattening the narrow sun band.
        face_shadow = face * smoothstep(.072, .018, luminance(linear))
        linear = apply_local_ev(linear, face_shadow, 1.18)
        tile_patch = ellipse_mask(shape, (.03, .43, .25, .25))
        linear = apply_local_ev(linear, tile_patch, -.32)
    return linear


def filmic_to_srgb(linear: np.ndarray, exposure_ev: float, white_point: float) -> np.ndarray:
    exposed = np.maximum(linear, 0.0) * np.exp2(exposure_ev)
    white_scale = white_point / (1.0 + white_point)
    compressed = np.clip((exposed / (1.0 + exposed)) / white_scale, 0.0, 1.0)
    low = compressed <= .0031308
    srgb = np.empty_like(compressed)
    srgb[low] = compressed[low] * 12.92
    srgb[~low] = 1.055 * np.power(compressed[~low], 1.0 / 2.4) - .055
    return np.clip(srgb, 0.0, 1.0)


def chroma_denoise(rgb: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return rgb
    lab = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2LAB)
    lab[..., 1] = cv2.GaussianBlur(lab[..., 1], (0, 0), sigma)
    lab[..., 2] = cv2.GaussianBlur(lab[..., 2], (0, 0), sigma)
    return np.clip(cv2.cvtColor(lab, cv2.COLOR_LAB2RGB), 0.0, 1.0)


def monochrome(rgb: np.ndarray) -> np.ndarray:
    # Red-sensitive skin rendering with enough green for natural tonal separation.
    return np.clip(rgb[..., 0] * .45 + rgb[..., 1] * .40 + rgb[..., 2] * .15, 0.0, 1.0)


def quantile_map_gray(gray: np.ndarray, spec: Target) -> np.ndarray:
    probs = np.array([.0, .01, .25, .50, .75, .99, 1.0], np.float64)
    src = np.quantile(gray, probs)
    dst = np.array([spec.minimum, spec.p01, spec.p25, spec.p50, spec.p75, spec.p99, spec.maximum], np.float64)
    # H2 eliminates most plateaus; this guard handles any remaining repeated values.
    keep = np.r_[True, np.diff(src) > 1e-6]
    x = src[keep]
    y = dst[keep]
    if x[0] > 0:
        x = np.r_[0.0, x]
        y = np.r_[spec.minimum, y]
    if x[-1] < 1:
        x = np.r_[x, 1.0]
        y = np.r_[y, spec.maximum]
    y = np.maximum.accumulate(y)
    curve = PchipInterpolator(x, y, extrapolate=True)
    return np.clip(curve(np.clip(gray, x[0], x[-1])).astype(np.float32), 0.0, 1.0)


def quantile_map_color(rgb: np.ndarray, spec: Target) -> np.ndarray:
    old = luminance(rgb)
    new = quantile_map_gray(old, spec)
    ratio = np.clip(new / np.maximum(old, 1e-4), 0.0, 40.0)
    mixed = rgb * ratio[..., None]
    # For the very darkest colored pixels, introduce a neutral floor rather than
    # leaving mathematically black channels unable to follow the lifted toe.
    residual = np.maximum(new - luminance(mixed), 0.0)
    mixed += residual[..., None]
    return np.clip(mixed, 0.0, 1.0)


def shift_foliage_to_olive(rgb: np.ndarray, pale: bool = False) -> np.ndarray:
    hsv = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2HSV)
    hue = hsv[..., 0]
    green = smoothstep(45.0, 85.0, hue) * (1.0 - smoothstep(150.0, 190.0, hue))
    hsv[..., 0] = np.mod(hue - green * (22.0 if not pale else 16.0), 360.0)
    hsv[..., 1] *= (0.88 if not pale else 0.70) * (1.0 - green * .24)
    hsv[..., 1] = np.clip(hsv[..., 1], 0.0, 1.0)
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)


def faded_grade(rgb: np.ndarray, pale: bool = False) -> np.ndarray:
    rgb = shift_foliage_to_olive(rgb, pale=pale)
    y = luminance(rgb)
    shadow = np.clip((.55 - y) / .55, 0.0, 1.0) ** 1.3
    high = np.clip((y - .35) / .65, 0.0, 1.0) ** 1.2
    gains = np.ones_like(rgb)
    gains[..., 0] += shadow * (.045 if not pale else .025) + high * .025
    gains[..., 1] += shadow * .010 + high * .012
    gains[..., 2] -= shadow * .025 + high * (.045 if not pale else .030)
    out = np.clip(rgb * gains, 0.0, 1.0)
    # Warm cream veil and restored analog chroma; the cool H2 base is otherwise
    # too gray compared with the supplied olive/cream film reference.
    hsv = cv2.cvtColor(out.astype(np.float32), cv2.COLOR_RGB2HSV)
    hsv[..., 1] = np.clip(hsv[..., 1] * (1.62 if not pale else 1.28), 0.0, .72)
    out = np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)
    warmth = np.array([.050, .022, -.040], np.float32)
    if pale:
        warmth *= .62
    return np.clip(out + warmth, 0.0, 1.0)


def post_tone_dodge(rgb: np.ndarray, number: str, look: Look, face: tuple[float, float, float, float] | None) -> np.ndarray:
    """Place key facial values after the master curve, like a darkroom dodge."""
    if face is None:
        return rgb
    mask = ellipse_mask(rgb.shape[:2], face, feather=2.4)
    y = luminance(rgb)
    # The multiplier is confined to darker face values, preserving bright cheek detail.
    shadow = np.clip((.56 - y) / .56, 0.0, 1.0) ** 1.4
    if number == "0496" and look.mode == "bw":
        gain = 1.0 + mask * shadow * .48
    elif number == "0875" and look.grade == "cinema":
        gain = 1.0 + mask * np.clip((.27 - y) / .27, 0.0, 1.0) ** 1.5 * .25
    else:
        return rgb
    return np.clip(rgb * gain[..., None], 0.0, 1.0)


def cinematic_grade(rgb: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    # Protect warm skin by hue; the striped dress and kitchen remain eligible for teal.
    lab = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2LAB)
    skin = smoothstep(3.0, 9.0, lab[..., 1]) * smoothstep(5.0, 18.0, lab[..., 2])
    skin = cv2.GaussianBlur(skin.astype(np.float32), (0, 0), 9.0)
    y = luminance(rgb)
    mid = np.clip(1.0 - np.abs(y - .38) / .38, 0.0, 1.0) ** 1.15
    high = np.clip((y - .38) / .62, 0.0, 1.0) ** 1.15
    teal = mid * (1.0 - skin * .90)
    warm = high * (.25 + .75 * skin)
    gains = np.ones_like(rgb)
    gains[..., 0] += warm * .115 - teal * .085
    gains[..., 1] += warm * .025 + teal * .018
    gains[..., 2] -= warm * .155
    gains[..., 2] += teal * .125
    out = np.clip(rgb * gains, 0.0, 1.0)
    # Restrained warm bloom follows only the directional highlight bands.
    bright = np.clip((luminance(out) - .52) / .48, 0.0, 1.0)
    glow = cv2.GaussianBlur(bright, (0, 0), 14.0) * skin
    warmth = np.array([1.0, .68, .35], np.float32)
    out = np.clip(out + glow[..., None] * warmth * .018, 0.0, 1.0)
    hsv = cv2.cvtColor(out.astype(np.float32), cv2.COLOR_RGB2HSV)
    hsv[..., 1] = np.clip(hsv[..., 1] * 1.34, 0.0, .78)
    return np.clip(cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB), 0.0, 1.0)


def apply_vignette(rgb: np.ndarray, amount: float) -> np.ndarray:
    if amount <= 0:
        return rgb
    h, w = rgb.shape[:2]
    yy = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    xx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    radius = np.sqrt(xx * xx + yy * yy)
    edge = np.clip((radius - .33) / .98, 0.0, 1.0) ** 1.7
    return np.clip(rgb * (1.0 - amount * edge[..., None]), 0.0, 1.0)


def texture_finish(rgb: np.ndarray, face: tuple[float, float, float, float] | None, clarity: float, sharpen: float) -> np.ndarray:
    protect = ellipse_mask(rgb.shape[:2], face, feather=1.45) if face else np.zeros(rgb.shape[:2], np.float32)
    if clarity:
        broad = cv2.GaussianBlur(rgb, (0, 0), 14.0)
        amount = clarity * (1.0 - protect * .78)
        rgb = np.clip(rgb + (rgb - broad) * amount[..., None], 0.0, 1.0)
    if sharpen:
        fine = cv2.GaussianBlur(rgb, (0, 0), 1.0)
        y = luminance(rgb)
        safe = (1.0 - smoothstep(.82, .98, y)) * (1.0 - smoothstep(0.0, .035, .035 - y))
        amount = sharpen * (1.0 - protect * .35) * safe
        rgb = np.clip(rgb + (rgb - fine) * amount[..., None], 0.0, 1.0)
    return rgb


def add_multiscale_grain(rgb: np.ndarray, amount: float, seed: int, monochrome_output: bool) -> np.ndarray:
    if amount <= 0:
        return rgb
    rng = np.random.default_rng(seed)
    h, w = rgb.shape[:2]
    fine = rng.normal(0.0, 1.0, (h, w)).astype(np.float32)
    coarse = cv2.GaussianBlur(rng.normal(0.0, 1.0, (h, w)).astype(np.float32), (0, 0), 1.25)
    noise = fine * .72 + coarse * .55
    y = luminance(rgb)
    envelope = np.sqrt(np.clip(1.0 - np.abs(y - .48) * 1.48, .16, 1.0))
    noise = noise * envelope * amount
    if monochrome_output:
        return np.clip(rgb + noise[..., None], 0.0, 1.0)
    # Luminance-only color grain keeps shadow chroma controlled.
    old = np.maximum(y, 1e-4)
    new = np.clip(y + noise, 0.0, 1.0)
    return np.clip(rgb * (new / old)[..., None], 0.0, 1.0)


def save_jpeg(rgb: np.ndarray, path: Path, quality: int = 97) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(np.round(rgb * 255.0), 0, 255).astype(np.uint8)
    image = Image.fromarray(data, "RGB")
    image.save(path, "JPEG", quality=quality, subsampling=0, optimize=True, icc_profile=srgb_profile_bytes())


def save_before(number: str, crop: tuple[int, int, int, int]) -> None:
    source = Image.open(SOURCE_JPG_DIR / f"DSCF{number}.jpg").convert("RGB")
    before = source.crop(crop)
    BEFORE_DIR.mkdir(parents=True, exist_ok=True)
    before.save(
        BEFORE_DIR / f"DSCF{number}_before.jpg", "JPEG", quality=96,
        subsampling=0, optimize=True, icc_profile=srgb_profile_bytes(),
    )


def metrics(rgb: np.ndarray) -> dict[str, object]:
    y = luminance(rgb)
    q = np.quantile(y, [.01, .25, .5, .75, .99])
    hsv = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2HSV)
    return {
        "dimensions": [int(rgb.shape[1]), int(rgb.shape[0])],
        "p01_p25_p50_p75_p99": [round(float(v), 5) for v in q],
        "below_0.005_percent": round(float(np.mean(y < .005) * 100), 5),
        "above_0.995_percent": round(float(np.mean(y > .995) * 100), 5),
        "saturation_median": round(float(np.median(hsv[..., 1])), 5),
        "saturation_p75": round(float(np.quantile(hsv[..., 1], .75)), 5),
    }


def prepare(number: str, recipe: Recipe) -> np.ndarray:
    linear = read_linear_crop(BASE_DIR / f"DSCF{number}.tiff", recipe.crop)
    if recipe.use_h2:
        companion = read_linear_crop(H2_DIR / f"DSCF{number}_H2.tiff", recipe.crop)
        linear = merge_highlights(linear, companion)
        del companion
    linear = source_adjustments(number, linear, recipe)
    srgb = filmic_to_srgb(linear, recipe.exposure_ev, recipe.white_point)
    return chroma_denoise(srgb, recipe.chroma_sigma)


def render_look(number: str, prepared: np.ndarray, recipe: Recipe, look: Look, index: int) -> np.ndarray:
    if look.mode == "bw":
        gray = quantile_map_gray(monochrome(prepared), look.target)
        out = np.repeat(gray[..., None], 3, axis=2)
    else:
        out = quantile_map_color(prepared, look.target)
        if look.grade == "faded":
            out = faded_grade(out)
        elif look.grade == "pale":
            out = faded_grade(out, pale=True)
        elif look.grade == "cinema":
            out = cinematic_grade(out, out.shape[:2])
    out = post_tone_dodge(out, number, look, recipe.face)
    out = apply_vignette(out, look.vignette)
    out = texture_finish(out, recipe.face, look.clarity, look.sharpen)
    out = add_multiscale_grain(out, look.grain, int(number) * 10 + index, look.mode == "bw")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("numbers", nargs="*", help="four-digit frame numbers")
    parser.add_argument("--variant", choices=("A", "B", "both"), default="both")
    args = parser.parse_args()
    numbers = args.numbers or list(RECIPES)
    all_metrics: dict[str, object] = {}
    for number in numbers:
        recipe = RECIPES[number]
        save_before(number, recipe.crop)
        prepared = prepare(number, recipe)
        for index, look in enumerate(recipe.looks):
            letter = "A" if index == 0 else "B"
            if args.variant != "both" and args.variant != letter:
                continue
            out = render_look(number, prepared, recipe, look, index)
            filename = f"DSCF{number}_{look.name}.jpg"
            save_jpeg(out, LOOK_DIR / filename)
            all_metrics[filename] = metrics(out)
            print(f"rendered {filename}")
            del out
        del prepared
    old = {}
    if METRICS_PATH.exists():
        old = json.loads(METRICS_PATH.read_text())
    old.update(all_metrics)
    METRICS_PATH.write_text(json.dumps(old, indent=2, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
