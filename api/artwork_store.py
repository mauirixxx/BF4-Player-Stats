"""Validated, versioned BF4 equipment artwork storage.

No network access or database writes. An authenticated HTTP layer must enforce
authorization, CSRF, Origin, rate limits and a strict upload byte ceiling.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import os
from pathlib import Path
import re
import secrets
from threading import RLock

from PIL import Image, ImageOps, UnidentifiedImageError

KINDS = frozenset(('weapon', 'vehicle'))
ROLES = frozenset(('fancy', 'hud'))
KEY_PATTERN = re.compile(r'^WARSAW_ID_[A-Z0-9_]{3,160}$')
MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_PIXELS = 8_000_000
MAX_SIDE = 4096
MAX_OUTPUT_BYTES = 2 * 1024 * 1024
_LOCK = RLock()


def validate_identity(kind, raw_key, role):
    if kind not in KINDS or role not in ROLES or not isinstance(raw_key, str) or not KEY_PATTERN.fullmatch(raw_key):
        raise ValueError('Invalid equipment identity')
    return kind + '-' + raw_key


def allowed_keys(artwork_js):
    """Read the shipped equipment-artwork catalog without executing JavaScript."""
    source = Path(artwork_js).read_text(encoding='utf-8')
    prefix = 'const equipmentArtwork='
    if not source.startswith('/*'):
        raise ValueError('Unexpected artwork catalog header')
    pos = source.find(prefix)
    if pos < 0:
        raise ValueError('Artwork catalog not found')
    raw = source[pos + len(prefix):].strip().removesuffix(';')
    data = json.loads(raw)
    return frozenset(data)


def verify_catalog(kind, raw_key, role, catalog):
    identity = validate_identity(kind, raw_key, role)
    if identity not in catalog:
        raise ValueError('Unknown equipment key')
    return identity


def transcode_image(raw):
    if not isinstance(raw, bytes) or not 0 < len(raw) <= MAX_INPUT_BYTES:
        raise ValueError('Image exceeds upload limit or is empty')
    try:
        with Image.open(BytesIO(raw)) as img:
            if img.format not in ('PNG', 'JPEG', 'WEBP') or getattr(img, 'n_frames', 1) != 1:
                raise ValueError('Only static PNG, JPEG or WebP images are supported')
            width, height = img.size
            if not (1 <= width <= MAX_SIDE and 1 <= height <= MAX_SIDE and width * height <= MAX_PIXELS):
                raise ValueError('Image dimensions exceed limits')
            img.load()
            image = ImageOps.exif_transpose(img).convert('RGBA')
        out = BytesIO()
        image.save(out, format='WEBP', quality=88, method=4)
        result = out.getvalue()
        if len(result) > MAX_OUTPUT_BYTES:
            raise ValueError('Processed image exceeds limit')
        return result, (image.width, image.height)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Invalid or oversized image') from exc


def _atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with open(temporary, 'x', encoding='utf-8') as stream:
            os.chmod(temporary, 0o600)
            json.dump(payload, stream, separators=(',', ':'), sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ArtworkStore:
    def __init__(self, private_root, public_root, catalog):
        self.private_root = Path(private_root)
        self.public_root = Path(public_root)
        self.catalog = frozenset(catalog)

    def _manifest_path(self):
        return self.public_root / 'manifest.json'

    def manifest(self):
        path = self._manifest_path()
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data, dict):
            raise ValueError('Invalid artwork manifest')
        return data

    def history(self, kind, raw_key, role):
        identity = verify_catalog(kind, raw_key, role, self.catalog)
        path = self.private_root / 'history.json'
        if not path.exists():
            return []
        entries = json.loads(path.read_text(encoding='utf-8'))
        return [item for item in entries if item['identity'] == identity and item['role'] == role]

    def publish(self, kind, raw_key, role, raw, actor):
        identity = verify_catalog(kind, raw_key, role, self.catalog)
        if not isinstance(actor, str) or not actor or len(actor) > 128:
            raise ValueError('Invalid actor')
        converted, (width, height) = transcode_image(raw)
        version = secrets.token_hex(16)
        filename = version + '.webp'
        with _LOCK:
            self.public_root.mkdir(parents=True, exist_ok=True)
            self.private_root.mkdir(parents=True, exist_ok=True)
            asset = self.public_root / filename
            with open(asset, 'xb') as stream:
                stream.write(converted)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(asset, 0o644)
            manifest = self.manifest()
            entry = dict(manifest.get(identity, {}))
            url = '/assets/equipment-overrides/' + filename
            entry[role] = {'local': url}
            manifest[identity] = entry
            history_path = self.private_root / 'history.json'
            history = json.loads(history_path.read_text()) if history_path.exists() else []
            history.append({'identity': identity, 'role': role, 'action': 'publish',
                            'actor': actor, 'version': version, 'sha256': sha256(converted).hexdigest(),
                            'width': width, 'height': height,
                            'at': datetime.now(timezone.utc).isoformat()})
            _atomic_json(history_path, history)
            _atomic_json(self._manifest_path(), manifest)
            return {'url': url, 'version': version}

    def restore(self, kind, raw_key, role, actor):
        identity = verify_catalog(kind, raw_key, role, self.catalog)
        if not isinstance(actor, str) or not actor or len(actor) > 128:
            raise ValueError('Invalid actor')
        with _LOCK:
            manifest = self.manifest()
            entry = dict(manifest.get(identity, {}))
            if role not in entry:
                return {'changed': False}
            entry.pop(role)
            if entry:
                manifest[identity] = entry
            else:
                manifest.pop(identity, None)
            history_path = self.private_root / 'history.json'
            history = json.loads(history_path.read_text()) if history_path.exists() else []
            history.append({'identity': identity, 'role': role, 'action': 'restore',
                            'actor': actor, 'at': datetime.now(timezone.utc).isoformat()})
            _atomic_json(history_path, history)
            _atomic_json(self._manifest_path(), manifest)
            return {'changed': True}
