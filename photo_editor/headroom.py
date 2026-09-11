"""Read-only sensor diagnostics. No demosaicing, WB or recipe is applied."""
from pathlib import Path
from functools import lru_cache
import sys
import threading
import numpy as np

_lock = threading.Lock()

def summarize(raw, colors, black, white, names="RGBG", period=2):
    if raw.ndim != 2 or colors.shape != raw.shape:
        raise ValueError("Sensor analysis currently supports mosaic RAW files only")
    channels=[]
    total=raw.size
    sat_count=black_count=weak_count=near_count=0
    # Sparse, same-color neighbor differences. Coprime sampling avoids fixing
    # analysis on one Bayer/X-Trans phase. Texture also contributes to variation.
    a=raw[::7,:-period:7].astype(np.float32)
    b=raw[::7,period::7].astype(np.float32)
    ca=colors[::7,:-period:7];cb=colors[::7,period::7]
    for c in np.unique(colors):
        c=int(c)
        if c>=len(black) or c>=len(white) or white[c]<=black[c]:
            raise ValueError("Usable sensor black/white levels are unavailable")
        values=raw[colors==c].astype(np.float32)
        span=float(white[c]-black[c]);signal=(values-black[c])/span
        saturated=int(np.count_nonzero(values>=white[c]))
        at_black=int(np.count_nonzero(values<=black[c]))
        weak=int(np.count_nonzero((signal>0)&(signal<1/256)))
        near=int(np.count_nonzero((signal>=.5)&(signal<1)))
        sat_count+=saturated;black_count+=at_black;weak_count+=weak;near_count+=near
        quantile=float(np.quantile(np.clip(signal,0,None),.999))
        mask=(ca==c)&(cb==c)&(a>black[c])&(b>black[c])&(a<black[c]+span*.01)&(b<black[c]+span*.01)
        residual=(a-b)[mask]
        sigma=None;ratio=None
        if residual.size>=128:
            estimate=float(np.median(np.abs(residual-np.median(residual)))/(.67448975*np.sqrt(2)))
            if estimate>0:
                sigma=estimate;ratio=float(np.median(((a+b)*.5-black[c])[mask])/sigma)
        channels.append({"channel":f"{names[c] if c<len(names) else 'C'}{c}","samples":int(values.size),
                         "black_level":float(black[c]),"white_level":float(white[c]),
                         "saturated_percent":100*saturated/values.size,
                         "at_black_percent":100*at_black/values.size,
                         "p999_headroom_ev":max(0.,float(-np.log2(quantile))) if quantile>0 else None,
                         "dark_variation_dn":sigma,"dark_signal_variation_ratio":ratio,
                         "dark_pairs":int(residual.size)})
    return {"sensor_samples":int(total),"channels":channels,
            "saturated_percent":100*sat_count/total,"at_black_percent":100*black_count/total,
            "weak_signal_percent":100*weak_count/total,"within_one_stop_percent":100*near_count/total}

def analyze(path):
    p=Path(path).expanduser().resolve();s=p.stat()
    with _lock:
        return _analyze(str(p),s.st_size,s.st_mtime_ns)

@lru_cache(maxsize=12)
def _analyze(path,size,mtime):
    deps=str(Path(__file__).parent/'editor_data'/'analysis_deps')
    if deps not in sys.path:sys.path.insert(0,deps)
    try:
        import rawpy
    except ImportError as exc:
        raise ValueError("Install the optional RAW diagnostics dependency; see README") from exc
    with rawpy.imread(path) as r:
        white=r.camera_white_level_per_channel
        origin="camera metadata per-channel white levels" if white else "LibRaw nominal white level (metadata/calibration dependent)"
        white=white or [r.white_level]*4
        pattern=r.raw_pattern
        period=int(pattern.shape[1]) if pattern is not None else 2
        result=summarize(r.raw_image_visible,r.raw_colors_visible,r.black_level_per_channel,white,r.color_desc.decode('ascii',errors='replace'),period)
        return {**result,"version":1,"white_level_source":origin,"decoder":f"rawpy {rawpy.__version__}",
                "scope":"Entire visible sensor mosaic; excludes margins; ignores crop, orientation and edits."}
