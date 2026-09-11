"""CPU I/O only for the shared GPU editor: float transport and tagged JPG encoding."""
from pathlib import Path
import numpy as np
from PIL import Image
from engine import load_image, jpeg_bytes


def source_pixels(path: str, limit: int):
    image = load_image(path)  # Never silently downsample an export/working source.
    if max(image.size) > limit:
        raise ValueError(f'Photo {image.width} x {image.height} exceeds GPU limit {limit}')
    rgba = np.ones((image.height, image.width, 4), dtype='<f4')
    rgba[..., :3] = image.pixels
    return rgba.tobytes(), image.width, image.height, image.source_bits, image.source_kind


def save_jpg(payload: bytes, width: int, height: int, source: str,
             destination: str, prefix: str, quality: int):
    if not (1 <= width <= 16384 and 1 <= height <= 16384) or width * height > 120_000_000:
        raise ValueError('Invalid export dimensions')
    if len(payload) != width * height * 4:
        raise ValueError('Incomplete GPU pixel buffer')
    if '/' in prefix or '\\' in prefix or '\x00' in prefix or len(prefix) > 100:
        raise ValueError('Export prefix must be a filename prefix, not a path')
    original = Path(source).expanduser().resolve(strict=True)
    folder = Path(destination).expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    image = Image.frombytes('RGBA', (width, height), payload).convert('RGB')
    encoded = jpeg_bytes(image, max(1, min(100, quality)))
    counter = 1
    while True:
        suffix = '' if counter == 1 else f'_{counter}'
        out = folder / f'{prefix}{original.stem}{suffix}.jpg'
        try:
            # Exclusive creation: neither originals nor previous exports are overwritten.
            with out.open('xb') as f:
                f.write(encoded)
            return str(out)
        except FileExistsError:
            counter += 1
