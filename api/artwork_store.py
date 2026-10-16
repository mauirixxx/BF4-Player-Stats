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


def allowed_keys(artwork_js, labels_js=None):
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
    if labels_js:
        labels_source = Path(labels_js).read_text(encoding='utf-8')
        label_marker = 'const equipmentLabels='
        label_pos = labels_source.find(label_marker)
        if label_pos < 0:
            raise ValueError('Equipment labels catalog not found')
        labels = json.loads(labels_source[label_pos + len(label_marker):].strip().removesuffix(';'))
        data.update({kind + '-' + key: {} for key in labels for kind in (('vehicle',) if '_VNAME_' in key else ('weapon',)) if kind + '-' + key not in data})
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


def _atomic_public_json(path, payload):
    temporary = path.with_name('.' + path.name + '.' + secrets.token_hex(8) + '.tmp')
    try:
        with open(temporary, 'x', encoding='utf-8') as stream:
            json.dump(payload, stream, separators=(',', ':'), sort_keys=True)
        os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ArtworkStore:
    """Publish in-place after timestamped backup; never accept client paths."""

    def __init__(self, private_root, public_root, catalog, artwork_catalog=None):
        self.private_root = Path(private_root)
        self.public_root = Path(public_root)
        self.catalog = frozenset(catalog)
        self.artwork_catalog = Path(artwork_catalog) if artwork_catalog else None

    def _paths(self, kind, raw_key, role):
        identity = verify_catalog(kind, raw_key, role, self.catalog)
        if self.artwork_catalog is None:
            raise RuntimeError('Artwork catalog path required')
        source = self.artwork_catalog.read_text(encoding='utf-8')
        marker = 'const equipmentArtwork='
        start = source.find(marker)
        if start < 0:
            raise ValueError('Invalid artwork catalog')
        data = json.loads(source[start + len(marker):].strip().removesuffix(';'))
        local = data.get(identity, {}).get(role, {}).get('local', '')
        prefix = '/assets/equipment/'
        if not local:
            filename = kind + '-' + sha256(raw_key.encode()).hexdigest()[:20] + '-' + role + '.webp'
            return identity, self.public_root / filename
        if not local.startswith(prefix):
            raise ValueError('Invalid artwork URL')
        filename = local[len(prefix):]
        if not re.fullmatch(r'[A-Za-z0-9_-]+\.webp', filename):
            raise ValueError('Invalid original artwork filename')
        return identity, self.public_root / filename

    def manifest(self):
        # Only newly introduced images require a public catalog overlay.
        history_path = self.private_root / 'history.json'
        if not history_path.exists():
            return {}
        history = json.loads(history_path.read_text(encoding='utf-8'))
        result = {}
        for entry in history:
            identity, role = entry['identity'], entry['role']
            kind, raw_key = identity.split('-', 1)
            _, asset = self._paths(kind, raw_key, role)
            if entry['action'] == 'restore' and entry.get('sha256') == sha256(b'').hexdigest():
                result.get(identity, {}).pop(role, None)
            elif entry['action'] == 'publish' and entry.get('backup') is None:
                result.setdefault(identity, {})[role] = {'local': '/assets/equipment/' + asset.name}
        return {key: value for key, value in result.items() if value}

    def _write_public_manifest(self):
        _atomic_public_json(self.public_root / 'artwork-added.json', self.manifest())

    def history(self, kind, raw_key, role):
        identity = verify_catalog(kind, raw_key, role, self.catalog)
        path = self.private_root / 'history.json'
        if not path.exists():
            return []
        entries = json.loads(path.read_text(encoding='utf-8'))
        return [item for item in entries if item['identity'] == identity and item['role'] == role]

    def _backup(self, asset):
        if asset.is_symlink():
            raise ValueError('Original artwork is unsafe')
        if not asset.is_file():
            return None
        backup_dir = self.private_root / 'backups'
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f')
        backup = backup_dir / (asset.stem + '-' + stamp + asset.suffix)
        with open(asset, 'rb') as source, open(backup, 'xb') as target:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        os.chmod(backup, 0o600)
        return backup

    def _replace(self, asset, data):
        temporary = asset.with_name('.' + asset.name + '.' + secrets.token_hex(8) + '.tmp')
        try:
            with open(temporary, 'xb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, 0o644)
            os.replace(temporary, asset)
        finally:
            temporary.unlink(missing_ok=True)

    def _record(self, identity, role, actor, action, backup, data):
        history_path = self.private_root / 'history.json'
        history = json.loads(history_path.read_text()) if history_path.exists() else []
        history.append({'identity': identity, 'role': role, 'action': action,
                        'actor': actor, 'backup': backup.name if backup else None,
                        'sha256': sha256(data).hexdigest(),
                        'at': datetime.now(timezone.utc).isoformat()})
        _atomic_json(history_path, history)

    def publish(self, kind, raw_key, role, raw, actor):
        identity, asset = self._paths(kind, raw_key, role)
        if not isinstance(actor, str) or not actor or len(actor) > 128:
            raise ValueError('Invalid actor')
        converted, dimensions = transcode_image(raw)
        with _LOCK:
            self.private_root.mkdir(parents=True, exist_ok=True)
            backup = self._backup(asset)
            self._replace(asset, converted)
            self._record(identity, role, actor, 'publish', backup, converted)
            self._write_public_manifest()
        return {'url': '/assets/equipment/' + asset.name,
                'version': sha256(converted).hexdigest()[:16]}

    def restore(self, kind, raw_key, role, actor):
        identity, asset = self._paths(kind, raw_key, role)
        if not isinstance(actor, str) or not actor or len(actor) > 128:
            raise ValueError('Invalid actor')
        with _LOCK:
            history = self.history(kind, raw_key, role)
            if not history or history[-1]['action'] == 'restore':
                return {'changed': False}
            # Restore the original pre-edit image, not the previous undo step.
            latest = next((entry for entry in history if entry['action'] == 'publish'), None)
            if latest is None:
                return {'changed': False}
            backup_name = latest.get('backup', '')
            if not re.fullmatch(r'[A-Za-z0-9_-]+\.webp', backup_name):
                raise ValueError('Invalid backup reference')
            backup_path = self.private_root / 'backups' / backup_name
            if not backup_path.is_file() or backup_path.is_symlink():
                raise ValueError('Backup is missing')
            data = backup_path.read_bytes()
            current_backup = self._backup(asset)
            self._replace(asset, data)
            self._record(identity, role, actor, 'restore', current_backup, data)
        return {'changed': True}
