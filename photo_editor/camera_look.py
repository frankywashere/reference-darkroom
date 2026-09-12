"""Approximate camera JPEG brightness/contrast without replacing RAW pixels."""
from pathlib import Path
import numpy as np
from engine import RAW_SUFFIXES, embedded_thumbnail, load_image, _srgb_to_linear, _lum


def fit_tone(raw, camera):
    # Distribution matching tolerates different orientation/camera crops. This
    # deliberately does not claim color-profile or local-tone reconstruction.
    percentiles = [10, 20, 35, 50, 65, 80, 90]
    x = np.percentile(_lum(raw), percentiles)
    y = np.percentile(_lum(camera), percentiles)
    good = (x > .0005) & (y > .0005) & (y < .95)
    if good.sum() < 3 or np.ptp(np.log2(x[good])) < .5:
        raise ValueError('Not enough tonal variation to estimate a camera-inspired look')
    a, b = np.polyfit(np.log2(x[good] / .18), np.log2(y[good] / .18), 1)
    gamma = float(np.clip(a, .5, 1.8))
    ev = float(np.clip(np.median(np.log2(y[good]/.18)-gamma*np.log2(x[good]/.18)), -3, 3))
    return {'version': 1, 'ev': ev, 'gamma': gamma,
            'method': 'Embedded camera JPEG brightness/contrast approximation'}


def camera_look(path):
    source = Path(path).expanduser().resolve(strict=True)
    if source.suffix.lower() not in RAW_SUFFIXES:
        raise ValueError('Camera-inspired analysis is for RAW files; JPEG already contains the camera look')
    jpeg = embedded_thumbnail(source, 640, require_embedded=True)
    camera = _srgb_to_linear(np.asarray(jpeg, dtype=np.float32)/255)
    return fit_tone(load_image(source, max_side=640).pixels, camera)
