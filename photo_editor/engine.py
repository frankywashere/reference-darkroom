from __future__ import annotations

import hashlib
import io
import json
import math
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageCms, ImageEnhance, ImageOps


IMAGE_SUFFIXES = {".raf", ".cr2", ".cr3", ".nef", ".arw", ".dng", ".jpg", ".jpeg", ".png", ".tif", ".tiff"}
RAW_SUFFIXES = {".raf", ".cr2", ".cr3", ".nef", ".arw", ".dng"}


@dataclass
class LinearImage:
    """Scene-linear RGB pixels kept as float32 until final encoding."""

    pixels: np.ndarray
    source_bits: int = 8
    source_kind: str = "RGB"

    def __post_init__(self) -> None:
        pixels = np.asarray(self.pixels, dtype=np.float32)
        if pixels.ndim != 3 or pixels.shape[2] != 3:
            raise ValueError("LinearImage pixels must be HxWx3 RGB")
        self.pixels = np.ascontiguousarray(pixels)

    @property
    def width(self) -> int:
        return int(self.pixels.shape[1])

    @property
    def height(self) -> int:
        return int(self.pixels.shape[0])

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height

    @property
    def nbytes(self) -> int:
        return int(self.pixels.nbytes)

    def copy(self) -> "LinearImage":
        return LinearImage(self.pixels.copy(), self.source_bits, self.source_kind)


PRESETS: dict[str, dict[str, Any]] = {
    "neutral": {"label": "Clean Neutral"},
    "cinematic": {"label": "Amber / Teal Cinema", "exposure": .15, "contrast": 18, "highlights": -32, "shadows": 20, "temperature": 9, "tint": -2, "vibrance": 18, "clarity": 9, "grain": 8, "vignette": 8, "grade": "cinema"},
    "gritty_bw": {"label": "Gritty Documentary B&W", "bw": True, "contrast": 30, "highlights": -14, "shadows": -12, "blacks": -22, "clarity": 15, "grain": 30, "vignette": 10, "bw_red": 52, "bw_green": 36, "bw_blue": 12},
    "refined_bw": {"label": "Refined Low-Key B&W", "bw": True, "exposure": -.25, "contrast": 26, "highlights": -18, "shadows": -34, "blacks": -18, "clarity": 6, "grain": 10, "vignette": 18, "bw_red": 46, "bw_green": 39, "bw_blue": 15},
    "highkey_bw": {"label": "Graphic High-Key B&W", "bw": True, "exposure": .55, "contrast": 16, "highlights": -20, "shadows": 36, "whites": 12, "blacks": -15, "clarity": 4, "grain": 6, "bw_red": 43, "bw_green": 42, "bw_blue": 15},
    "silhouette_bw": {"label": "Architectural Silhouette", "bw": True, "exposure": -.18, "contrast": 38, "highlights": -12, "shadows": -45, "whites": 15, "blacks": -22, "clarity": 8, "grain": 7, "vignette": 4},
    "faded_film": {"label": "Faded Warm Film", "exposure": .20, "contrast": -8, "highlights": -24, "shadows": 24, "blacks": 15, "temperature": 11, "tint": 3, "saturation": -7, "vibrance": 5, "clarity": -5, "grain": 20, "vignette": 6, "grade": "faded"},
}


DEFAULT_RECIPE: dict[str, Any] = {
    "preset": "neutral", "exposure": 0.0, "contrast": 0, "highlights": 0, "shadows": 0,
    "whites": 0, "blacks": 0, "temperature": 0, "tint": 0, "saturation": 0,
    "vibrance": 0, "clarity": 0, "dehaze": 0, "sharpen": 12, "denoise": 8,
    "grain": 0, "vignette": 0, "bw": False, "bw_red": 45, "bw_green": 40,
    "bw_blue": 15, "curve": [0, 25, 50, 75, 100], "rotation": 0, "straighten": 0,
    "flip_h": False, "flip_v": False, "crop": [0, 0, 1, 1], "masks": [], "grade": "neutral",
}


def normalize_recipe(recipe: dict[str, Any] | None) -> dict[str, Any]:
    out = dict(DEFAULT_RECIPE)
    supplied = recipe or {}
    preset = supplied.get("preset", "neutral")
    out.update(PRESETS.get(preset, {}))
    out.update(supplied)
    out.pop("label", None)
    out.pop("tone_engine", None)
    return out


def _srgb_profile() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def _srgb_to_linear(rgb: np.ndarray) -> np.ndarray:
    rgb = np.asarray(rgb, dtype=np.float32)
    return np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4).astype(np.float32)


def _linear_to_srgb(rgb: np.ndarray) -> np.ndarray:
    rgb = np.maximum(np.asarray(rgb, dtype=np.float32), 0)
    return np.where(rgb <= .0031308, rgb * 12.92, 1.055 * np.power(rgb, 1 / 2.4) - .055).astype(np.float32)


def _cv_rgb(path: Path) -> tuple[np.ndarray, int]:
    decoded = cv2.imread(str(path), cv2.IMREAD_UNCHANGED | cv2.IMREAD_ANYDEPTH | cv2.IMREAD_ANYCOLOR)
    if decoded is None:
        raise RuntimeError(f"Could not decode image: {path}")
    if decoded.ndim == 2:
        decoded = np.repeat(decoded[..., None], 3, axis=2)
    elif decoded.shape[2] == 4:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGRA2RGB)
    else:
        decoded = cv2.cvtColor(decoded, cv2.COLOR_BGR2RGB)
    if decoded.dtype == np.uint16:
        return decoded.astype(np.float32) / 65535.0, 16
    if decoded.dtype == np.uint8:
        return decoded.astype(np.float32) / 255.0, 8
    maximum = float(np.iinfo(decoded.dtype).max) if np.issubdtype(decoded.dtype, np.integer) else 1.0
    return decoded.astype(np.float32) / maximum, int(decoded.dtype.itemsize * 8)


def _decode_raw(path: Path, half: bool) -> LinearImage:
    with tempfile.TemporaryDirectory(prefix="frank_photo_editor_") as td:
        output = Path(td) / "decoded.tiff"
        # Preserve a 16-bit scene-linear master. -4 is dcraw_emu's shorthand for
        # -6 -W -g 1 1; -H 2 blends clipped channels when colour survives.
        command = ["dcraw_emu", "-w", "-q", "3", "-4", "-H", "2", "-T"]
        if half:
            command.append("-h")
        # LibRaw's dcraw_emu uses -Z for an explicit output path (unlike some
        # dcraw variants that accept -O).
        command.extend(["-Z", str(output), str(path)])
        proc = subprocess.run(command, capture_output=True, text=True, timeout=180)
        if proc.returncode or not output.exists():
            raise RuntimeError((proc.stderr or proc.stdout or "RAW decoder failed").strip())
        rgb, bits = _cv_rgb(output)
        # -4 retains the sensor's fixed white level, which commonly occupies only
        # a fraction of the 16-bit container. Establish a viewable baseline with
        # a pure float multiplier; values above 1.0 remain recoverable and are
        # never clipped here. The robust percentile is stable across preview/full
        # resolution decodes and avoids hot-pixel-driven exposure.
        sample = rgb
        if max(rgb.shape[:2]) > 640:
            scale = 640 / max(rgb.shape[:2])
            sample = cv2.resize(rgb, (max(1, round(rgb.shape[1] * scale)), max(1, round(rgb.shape[0] * scale))), interpolation=cv2.INTER_AREA)
        sample_luma = _lum(sample)
        reference_white = max(float(np.percentile(sample_luma, 99.5)), 1e-4)
        baseline_gain = float(np.clip(.90 / reference_white, 1, 128))
        return LinearImage(rgb * baseline_gain, max(bits, 16), "RAW linear")


def resize_linear(image: LinearImage, max_side: int | None) -> LinearImage:
    if not max_side or max(image.size) <= max_side:
        return image
    scale = max_side / max(image.size)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    pixels = cv2.resize(image.pixels, size, interpolation=cv2.INTER_AREA)
    return LinearImage(pixels, image.source_bits, image.source_kind)


def load_image(path: str | Path, max_side: int | None = None) -> LinearImage:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    if source.suffix.lower() in RAW_SUFFIXES:
        image = _decode_raw(source, half=bool(max_side and max_side <= 2600))
    else:
        suffix = source.suffix.lower()
        if suffix in {".tif", ".tiff", ".png"}:
            encoded, bits = _cv_rgb(source)
            image = LinearImage(_srgb_to_linear(encoded), bits, f"{bits}-bit RGB")
        else:
            with Image.open(source) as im:
                oriented = ImageOps.exif_transpose(im).convert("RGB")
                encoded = np.asarray(oriented, dtype=np.float32) / 255.0
            image = LinearImage(_srgb_to_linear(encoded), 8, "8-bit RGB")
    return resize_linear(image, max_side)


def embedded_thumbnail(path: str | Path, max_side: int = 420) -> Image.Image:
    source = Path(path).expanduser().resolve()
    if source.suffix.lower() in RAW_SUFFIXES:
        for tag in ("JpgFromRaw", "PreviewImage", "ThumbnailImage"):
            proc = subprocess.run(["exiftool", "-b", f"-{tag}", str(source)], capture_output=True, timeout=25)
            if proc.returncode == 0 and len(proc.stdout) > 1024:
                try:
                    image = ImageOps.exif_transpose(Image.open(io.BytesIO(proc.stdout))).convert("RGB")
                    image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
                    return image
                except Exception:
                    pass
    return linear_to_pil(load_image(source, max_side=max_side).pixels)


def _to_linear_image(image: LinearImage | Image.Image | np.ndarray) -> LinearImage:
    if isinstance(image, LinearImage):
        return image.copy()
    if isinstance(image, Image.Image):
        encoded = np.asarray(image.convert("RGB"), dtype=np.float32) / 255.0
        return LinearImage(_srgb_to_linear(encoded), 8, "8-bit RGB")
    pixels = np.asarray(image)
    if pixels.dtype == np.uint16:
        return LinearImage(_srgb_to_linear(pixels.astype(np.float32) / 65535.0), 16, "16-bit RGB")
    if pixels.dtype == np.uint8:
        return LinearImage(_srgb_to_linear(pixels.astype(np.float32) / 255.0), 8, "8-bit RGB")
    return LinearImage(pixels.astype(np.float32), 32, "float linear")


def linear_to_pil(rgb: np.ndarray) -> Image.Image:
    encoded = np.clip(_linear_to_srgb(rgb), 0, 1)
    return Image.fromarray(np.uint8(encoded * 255 + .5), "RGB")


def display_to_pil(rgb: np.ndarray) -> Image.Image:
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 1) * 255 + .5), "RGB")


def _lum(rgb: np.ndarray) -> np.ndarray:
    return rgb[..., 0] * .2126 + rgb[..., 1] * .7152 + rgb[..., 2] * .0722


def _smoothstep(edge0: float, edge1: float, values: np.ndarray) -> np.ndarray:
    if abs(edge1 - edge0) < 1e-6:
        return np.zeros_like(values)
    t = np.clip((values - edge0) / (edge1 - edge0), 0, 1)
    return t * t * (3 - 2 * t)

def _tone(rgb: np.ndarray, r: dict[str, Any]) -> np.ndarray:
    # One shared processing model, irrespective of legacy recipe version tags.
    rgb = np.maximum(rgb * (2.0 ** float(r["exposure"])), 0)
    exponent = max(.15, 1 + float(r["contrast"]) * .008)
    rgb = .18 * np.power(np.maximum(rgb / .18, 0), exponent)
    y = _lum(rgb)
    shadow = np.clip(float(r["shadows"]) / 100, -1, 1)
    high = np.clip(float(r["highlights"]) / 100, -1, 1)
    # Restore the original .28 shadow boundary, with up to 5 EV near black.
    # Both curves are monotonic, fix the boundary and have derivative 1 there:
    # extra strength cannot reverse tones or spill into brighter midtones.
    boundary = .28
    x = np.clip(y / boundary, 0, 1)
    k = np.expm1(abs(shadow) * 5 * np.log(2))
    low = x * (1 + k * (1 - x)) / (1 + k * x * (1 - x)) if shadow >= 0 else x / (1 + k * (1 - x) ** 2)
    mapped = np.where(y < boundary, boundary * low, y)
    # Logarithmic shoulder preserves tonal ordering without the old finite
    # ceiling. It acts on recorded intensity, never invents clipped detail.
    excess = np.maximum(mapped - .18, 0)
    if high < 0:
        k = -high * 8
        shoulder = .18 + np.log1p(k * excess) / k
    else:
        shoulder = .18 + excess * 2 ** (high * 2)
    mapped = np.where(mapped > .18, shoulder, mapped)
    rgb = rgb * (mapped / np.maximum(y, 1e-12))[..., None]
    black_w = np.clip((.075 - mapped) / .075, 0, 1)
    white_w = np.clip((mapped - .55) / .45, 0, 1)
    stops = black_w * float(r["blacks"]) * .012 + white_w * float(r["whites"]) * .012
    return np.clip(rgb * np.exp2(stops[..., None]), 0, 32)


def _temperature(rgb: np.ndarray, temperature: float, tint: float) -> np.ndarray:
    t = temperature / 100
    g = tint / 100
    gains = np.array([1 + t * .22 + g * .08, 1 - abs(g) * .04, 1 - t * .22 + g * .06], np.float32)
    return np.clip(rgb * gains, 0, 32)


def _color(rgb: np.ndarray, r: dict[str, Any]) -> np.ndarray:
    rgb = _temperature(rgb, float(r["temperature"]), float(r["tint"]))
    gray = _lum(rgb)[..., None]
    saturation = 1 + float(r["saturation"]) / 100
    rgb = gray + (rgb - gray) * saturation
    chroma = (np.max(rgb, axis=2) - np.min(rgb, axis=2)) / np.maximum(np.max(rgb, axis=2), 1e-5)
    vibrance = float(r["vibrance"]) / 100
    rgb = gray + (rgb - gray) * (1 + vibrance * (1 - chroma))[..., None]
    return np.clip(rgb, 0, 32)


def _grade(rgb: np.ndarray, grade: str) -> np.ndarray:
    y = _lum(rgb)
    if grade == "cinema":
        shadow = np.clip((.58 - y) / .58, 0, 1)
        high = np.clip((y - .38) / .62, 0, 1)
        rgb[..., 0] += high * .075 - shadow * .035
        rgb[..., 1] += shadow * .018 + high * .015
        rgb[..., 2] += shadow * .065 - high * .080
    elif grade == "faded":
        shadow = np.clip((.60 - y) / .60, 0, 1)
        high = np.clip((y - .35) / .65, 0, 1)
        rgb[..., 0] += shadow * .035 + high * .028
        rgb[..., 1] += high * .012
        rgb[..., 2] -= shadow * .020 + high * .038
        rgb = rgb * .94 + np.array([.035, .026, .014], np.float32)
    return np.clip(rgb, 0, 32)


def _curve(rgb: np.ndarray, points: list[float]) -> np.ndarray:
    if len(points) != 5:
        return rgb
    x = np.array([0, .25, .5, .75, 1], np.float32)
    y = np.maximum.accumulate(np.clip(np.asarray(points, np.float32) / 100, 0, 1))
    lut_x = np.linspace(0, 1, 1024, dtype=np.float32)
    lut = np.interp(lut_x, x, y)
    return np.interp(rgb, lut_x, lut).astype(np.float32)


def _brush_mask(shape: tuple[int, int], spec: dict[str, Any]) -> np.ndarray:
    """Replay resolution-independent dabs; only allocate each dab's bounding box."""
    h, w = shape
    result = np.zeros(shape, np.float32)
    for stroke in spec.get("strokes", []):
        coverage = np.zeros(shape, np.float32)
        radius = max(.001, min(1., float(stroke.get("size", .1)))) * min(w, h) / 2
        feather = np.clip(float(stroke.get("feather", 60)) / 100, .001, 1)
        strength = np.clip(float(stroke.get("flow", 50)) / 100, 0, 1)
        for x, y in stroke.get("points", []):
            cx, cy = x * w, y * h
            left, right = max(0, int(cx-radius)), min(w, int(math.ceil(cx+radius)))
            top, bottom = max(0, int(cy-radius)), min(h, int(math.ceil(cy+radius)))
            if right <= left or bottom <= top:
                continue
            yy, xx = np.ogrid[top:bottom, left:right]
            distance = np.sqrt((xx+.5-cx)**2 + (yy+.5-cy)**2) / radius
            alpha = (1 - np.clip((distance - (1-feather)) / feather, 0, 1)) * strength
            region = coverage[top:bottom, left:right]
            region += (1-region)*alpha
        coverage *= np.clip(float(stroke.get("opacity", 100)) / 100, 0, 1)
        if stroke.get("erase"):
            result *= 1-coverage
        else:
            result += (1-result)*coverage
    return result


def _mask(shape: tuple[int, int], spec: dict[str, Any]) -> np.ndarray:
    h, w = shape
    yy, xx = np.ogrid[:h, :w]
    kind = spec.get("type", "ellipse")
    feather = max(float(spec.get("feather", 60)) / 100, .02)
    if kind == "brush":
        result = _brush_mask(shape, spec)
    elif kind == "linear":
        angle = math.radians(float(spec.get("angle", 0)))
        x = xx / max(w - 1, 1) - float(spec.get("x", .5))
        y = yy / max(h - 1, 1) - float(spec.get("y", .5))
        d = x * math.cos(angle) + y * math.sin(angle)
        width = max(float(spec.get("size", .35)), .02)
        result = _smoothstep(width * .5, -width * .5, d)
    else:
        cx, cy = float(spec.get("x", .5)), float(spec.get("y", .5))
        rx = max(float(spec.get("width", .25)), .01)
        ry = max(float(spec.get("height", .25)), .01)
        d = np.sqrt(((xx / max(w - 1, 1) - cx) / rx) ** 2 + ((yy / max(h - 1, 1) - cy) / ry) ** 2)
        result = 1 - _smoothstep(max(0, 1 - feather), 1 + feather, d)
    if spec.get("invert"):
        result = 1 - result
    return np.clip(result, 0, 1).astype(np.float32)


def _local_masks(rgb: np.ndarray, masks: list[dict[str, Any]]) -> np.ndarray:
    for spec in masks:
        if spec.get("enabled") is False:
            continue
        weight = _mask(rgb.shape[:2], spec) * np.clip(float(spec.get("amount", 100)) / 100, 0, 1)
        ev = float(spec.get("exposure", 0))
        if ev:
            rgb *= np.exp2(ev * weight)[..., None]
        sat = float(spec.get("saturation", 0)) / 100
        if sat:
            gray = _lum(rgb)[..., None]
            adjusted = gray + (rgb - gray) * (1 + sat)
            rgb = rgb * (1 - weight[..., None]) + adjusted * weight[..., None]
        temp = float(spec.get("temperature", 0))
        if temp:
            adjusted = _temperature(rgb, temp, 0)
            rgb = rgb * (1 - weight[..., None]) + adjusted * weight[..., None]
        rgb = np.clip(rgb, 0, 32)
    return rgb


def _detail(rgb: np.ndarray, r: dict[str, Any], preview: bool) -> np.ndarray:
    denoise = max(float(r["denoise"]), 0) / 100
    if denoise:
        lab = cv2.cvtColor(rgb.astype(np.float32), cv2.COLOR_RGB2LAB)
        sigma = .4 + denoise * 2.2
        lab[..., 1] = cv2.GaussianBlur(lab[..., 1], (0, 0), sigma)
        lab[..., 2] = cv2.GaussianBlur(lab[..., 2], (0, 0), sigma)
        rgb = cv2.cvtColor(lab, cv2.COLOR_LAB2RGB)
    clarity = float(r["clarity"]) / 100
    dehaze = float(r["dehaze"]) / 100
    if clarity or dehaze:
        broad = cv2.GaussianBlur(rgb, (0, 0), 8 if preview else 16)
        rgb = np.clip(rgb + (rgb - broad) * (clarity * .7 + dehaze * 1.1), 0, 1)
    sharpen = max(float(r["sharpen"]), 0) / 100
    if sharpen:
        fine = cv2.GaussianBlur(rgb, (0, 0), .8)
        rgb = np.clip(rgb + (rgb - fine) * sharpen, 0, 1)
    return rgb


def _finish(rgb: np.ndarray, r: dict[str, Any], seed: int) -> np.ndarray:
    vignette = max(float(r["vignette"]), 0) / 100
    if vignette:
        h, w = rgb.shape[:2]
        yy = np.linspace(-1, 1, h, dtype=np.float32)[:, None]
        xx = np.linspace(-1, 1, w, dtype=np.float32)[None, :]
        edge = np.clip((np.sqrt(xx * xx + yy * yy) - .25) / 1.1, 0, 1) ** 1.6
        rgb *= 1 - edge[..., None] * vignette * .65
    grain = max(float(r["grain"]), 0) / 100
    if grain:
        rng = np.random.default_rng(seed)
        noise = rng.normal(0, grain * .045, rgb.shape[:2]).astype(np.float32)
        envelope = np.sqrt(np.clip(1 - np.abs(_lum(rgb) - .5), .25, 1))
        rgb += (noise * envelope)[..., None]
    return np.clip(rgb, 0, 1)


def _geometry(rgb: np.ndarray, r: dict[str, Any]) -> np.ndarray:
    if r.get("flip_h"):
        rgb = np.ascontiguousarray(rgb[:, ::-1])
    if r.get("flip_v"):
        rgb = np.ascontiguousarray(rgb[::-1])
    angle = float(r.get("rotation", 0)) + float(r.get("straighten", 0))
    if not angle:
        return rgb
    h, w = rgb.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), -angle, 1.0)
    cos_a, sin_a = abs(matrix[0, 0]), abs(matrix[0, 1])
    out_w, out_h = int(h * sin_a + w * cos_a), int(h * cos_a + w * sin_a)
    matrix[0, 2] += out_w / 2 - w / 2
    matrix[1, 2] += out_h / 2 - h / 2
    return cv2.warpAffine(rgb, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(.006, .006, .006))


def develop_linear(image: LinearImage | Image.Image | np.ndarray, recipe: dict[str, Any] | None) -> tuple[np.ndarray, dict[str, Any]]:
    """Apply scene-linear operations without clipping display highlights."""
    r = normalize_recipe(recipe)
    rgb = _geometry(_to_linear_image(image).pixels, r)
    rgb = _tone(rgb, r)
    rgb = _color(rgb, r)
    rgb = _grade(rgb, str(r.get("grade", "neutral")))
    rgb = _local_masks(rgb, list(r.get("masks", [])))
    if r.get("bw"):
        weights = np.array([float(r["bw_red"]), float(r["bw_green"]), float(r["bw_blue"])], np.float32)
        weights /= max(float(weights.sum()), 1)
        gray = np.sum(rgb * weights, axis=2)
        rgb = np.repeat(gray[..., None], 3, axis=2)
    return np.clip(rgb, 0, 32), r


def process_array(image: LinearImage | Image.Image | np.ndarray, recipe: dict[str, Any] | None,
                  *, apply_crop: bool = True, preview: bool = False, seed: int = 1) -> np.ndarray:
    """Return display-referred float32 RGB; quantization happens outside this function."""
    rgb, r = develop_linear(image, recipe)
    rgb = np.clip(_linear_to_srgb(rgb), 0, 1)
    rgb = _curve(rgb, list(r.get("curve", DEFAULT_RECIPE["curve"])))
    rgb = _detail(rgb, r, preview)
    rgb = _finish(rgb, r, seed)
    if apply_crop:
        crop = list(r.get("crop", [0, 0, 1, 1]))
        if len(crop) == 4:
            x, y, w, h = [float(v) for v in crop]
            height, width = rgb.shape[:2]
            left = round(np.clip(x, 0, 1) * width)
            top = round(np.clip(y, 0, 1) * height)
            right = round(np.clip(x + w, 0, 1) * width)
            bottom = round(np.clip(y + h, 0, 1) * height)
            if right - left > 10 and bottom - top > 10:
                rgb = rgb[top:bottom, left:right]
    return np.ascontiguousarray(rgb, dtype=np.float32)


def process(image: LinearImage | Image.Image | np.ndarray, recipe: dict[str, Any] | None,
            *, apply_crop: bool = True, preview: bool = False, seed: int = 1) -> Image.Image:
    return display_to_pil(process_array(image, recipe, apply_crop=apply_crop, preview=preview, seed=seed))


def clipping_stats(image: LinearImage | Image.Image | np.ndarray, recipe: dict[str, Any] | None) -> dict[str, float]:
    """Measure display clipping after edits while the underlying float data is intact."""
    rgb, _ = develop_linear(image, recipe)
    luminance = _lum(rgb)
    return {
        "highlight_percent": float(np.mean(np.max(rgb, axis=2) >= 1.0) * 100),
        "shadow_percent": float(np.mean(luminance <= .0005) * 100),
        "recoverable_highlight_percent": float(np.mean((np.max(rgb, axis=2) >= 1.0) & (np.min(rgb, axis=2) < 1.0)) * 100),
    }


def half_float_rgba(image: LinearImage) -> bytes:
    """Pack a high-precision linear preview for a WebGL2 RGBA16F texture."""
    rgba = np.ones((image.height, image.width, 4), dtype=np.float16)
    rgba[..., :3] = np.clip(image.pixels, 0, np.finfo(np.float16).max).astype(np.float16)
    return rgba.tobytes()


def jpeg_bytes(image: Image.Image, quality: int = 90) -> bytes:
    stream = io.BytesIO()
    image.save(stream, "JPEG", quality=int(quality), subsampling=0, optimize=True, icc_profile=_srgb_profile())
    return stream.getvalue()


def path_id(path: str | Path) -> str:
    return hashlib.sha1(str(Path(path).expanduser().resolve()).encode()).hexdigest()[:20]


def recipe_json(recipe: dict[str, Any]) -> str:
    return json.dumps(normalize_recipe(recipe), indent=2, sort_keys=True)
