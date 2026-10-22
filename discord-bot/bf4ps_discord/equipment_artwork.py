"""Read-only official equipment artwork lookup from the BF4PS website manifest.

Bounded, thread-safe in-process caches keep hot artwork and manifest lookups
off the website. Caches are per HA process; no database writes are required.
"""
import json
import threading
import time
import urllib.request
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed

BASE = "https://www.bf4playerstats.com"
MANIFEST = BASE + "/equipment-artwork.js"
_TTL = 6 * 3600
_MAX_ARTWORK_BYTES = 32 * 1024 * 1024
_MAX_IMAGES = 512
_lock = threading.RLock()
_manifest = {}
_manifest_until = 0.0
_images = OrderedDict()
_image_bytes = 0


def _get_manifest():
    global _manifest, _manifest_until
    with _lock:
        if time.monotonic() < _manifest_until:
            return _manifest
        request = urllib.request.Request(MANIFEST, headers={"User-Agent": "BF4PS-Discord/1.0"})
        with urllib.request.urlopen(request, timeout=4) as response:
            script = response.read(250_000).decode("utf-8")
        marker = "const equipmentArtwork="
        if marker not in script:
            raise ValueError("Equipment artwork manifest missing")
        _manifest = json.loads(script.split(marker, 1)[1].strip().removesuffix(";"))
        _manifest_until = time.monotonic() + _TTL
        return _manifest


def _image(path):
    global _image_bytes
    if not (path.startswith("/assets/equipment/") and
            path.lower().endswith((".png", ".webp", ".jpg", ".jpeg")) and
            ".." not in path and "?" not in path and "#" not in path):
        return None
    with _lock:
        hit = _images.get(path)
        if hit and time.monotonic() < hit[1]:
            _images.move_to_end(path)
            return hit[0]
        if hit:
            _image_bytes -= len(hit[0])
            del _images[path]
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "BF4PS-Discord/1.0"})
    with urllib.request.urlopen(req, timeout=5) as response:
        data = response.read(2_000_001)
    if len(data) > 2_000_000:
        return None
    with _lock:
        old = _images.pop(path, None)
        if old:
            _image_bytes -= len(old[0])
        _images[path] = (data, time.monotonic() + _TTL)
        _image_bytes += len(data)
        while len(_images) > _MAX_IMAGES or _image_bytes > _MAX_ARTWORK_BYTES:
            _, removed = _images.popitem(last=False)
            _image_bytes -= len(removed[0])
    return data


def fetch_equipment_artwork(kind: str, guid: str) -> bytes | None:
    if kind not in ("weapon", "vehicle"):
        return None
    if not guid or len(guid) > 160 or not all(c.isalnum() or c in "_-" for c in guid):
        return None
    path = _get_manifest().get(kind + "-" + guid, {}).get("fancy", {}).get("local", "")
    return _image(path)


def fetch_top_artwork(kind: str, localization_keys: list[str]) -> dict[str, bytes]:
    """Fetch up to nine images; cached assets avoid repeat HTTPS traffic."""
    if kind not in ("weapon", "vehicle"):
        return {}
    manifest = _get_manifest()
    paths = {}
    for key in localization_keys[:9]:
        if not key or len(key) > 160 or not all(c.isalnum() or c in "_-" for c in key):
            continue
        path = manifest.get(kind + "-" + key, {}).get("fancy", {}).get("local", "")
        if path:
            paths[key] = path

    found = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(_image, path): key for key, path in paths.items()}
        for future in as_completed(futures):
            try:
                data = future.result()
                if data:
                    found[futures[future]] = data
            except Exception:
                continue
    return found
