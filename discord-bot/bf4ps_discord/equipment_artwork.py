"""Read-only official equipment artwork lookup from the BF4PS website manifest."""
import json
import urllib.request

BASE = "https://www.bf4playerstats.com"
MANIFEST = BASE + "/equipment-artwork.js"


def fetch_equipment_artwork(kind: str, guid: str) -> bytes | None:
    if kind not in ('weapon', 'vehicle'):
        return None
    if not guid or len(guid) > 160 or not all(c.isalnum() or c in "_-" for c in guid):
        return None
    request = urllib.request.Request(MANIFEST, headers={"User-Agent": "BF4PS-Discord/1.0"})
    with urllib.request.urlopen(request, timeout=4) as response:
        script = response.read(250_000).decode("utf-8")
    marker = "const equipmentArtwork="
    if marker not in script:
        return None
    manifest = json.loads(script.split(marker, 1)[1].strip().removesuffix(";"))
    record = manifest.get(kind + "-" + guid, {})
    path = record.get("fancy", {}).get("local", "")
    if not path.startswith("/assets/equipment/") or not path.lower().endswith((".png", ".webp", ".jpg", ".jpeg")):
        return None
    if ".." in path or "?" in path or "#" in path:
        return None
    image_request = urllib.request.Request(BASE + path, headers={"User-Agent": "BF4PS-Discord/1.0"})
    with urllib.request.urlopen(image_request, timeout=5) as response:
        data = response.read(2_000_001)
    return data if len(data) <= 2_000_000 else None


def fetch_top_artwork(kind: str, localization_keys: list[str]) -> dict[str, bytes]:
    """Fetch up to nine fancy equipment images using one manifest request.

    Missing or broken assets are omitted. Only local website asset paths are used.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    if kind not in ("weapon", "vehicle"):
        return {}
    request = urllib.request.Request(MANIFEST, headers={"User-Agent": "BF4PS-Discord/1.0"})
    with urllib.request.urlopen(request, timeout=4) as response:
        script = response.read(250_000).decode("utf-8")
    marker = "const equipmentArtwork="
    if marker not in script:
        return {}
    manifest = json.loads(script.split(marker, 1)[1].strip().removesuffix(";"))
    paths = {}
    for key in localization_keys[:9]:
        record = manifest.get(kind + "-" + key, {})
        path = record.get("fancy", {}).get("local", "")
        if (path.startswith("/assets/equipment/") and
            path.lower().endswith((".png", ".webp", ".jpg", ".jpeg")) and
            ".." not in path and "?" not in path and "#" not in path):
            paths[key] = path

    def fetch(item):
        key, path = item
        req = urllib.request.Request(BASE + path, headers={"User-Agent": "BF4PS-Discord/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read(2_000_001)
        return key, data if len(data) <= 2_000_000 else None

    found = {}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, item) for item in paths.items()]
        for future in as_completed(futures):
            try:
                key, data = future.result()
                if data:
                    found[key] = data
            except Exception:
                continue
    return found
