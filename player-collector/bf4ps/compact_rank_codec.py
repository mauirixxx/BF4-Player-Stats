"""Versioned immutable compact-ranking payloads. No database side effects.

Scores are encoded as strings to preserve PostgreSQL numeric precision;
caller owns converting to Decimal/datetime for the public API.
"""
import json
import zlib

BLOCK_SIZE = 1000
MAGIC = b'BF4RC1\x00'


def encode_block(rows):
    """Encode ordered (soldier_id, rank, kills, kpm, accuracy, fetched_at) tuples."""
    if not 1 <= len(rows) <= BLOCK_SIZE:
        raise ValueError('block must contain 1..1000 rows')
    packed = []
    seen = set()
    for row in rows:
        if len(row) != 6:
            raise ValueError('expected six snapshot fields')
        soldier, rank, kills, kpm, accuracy, fetched_at = row
        if not isinstance(soldier, int) or soldier < 1 or soldier in seen:
            raise ValueError('invalid or repeated soldier')
        if not isinstance(rank, int) or rank < 1:
            raise ValueError('invalid rank')
        seen.add(soldier)
        packed.append([soldier, rank, kills, None if kpm is None else str(kpm),
                       None if accuracy is None else str(accuracy),
                       None if fetched_at is None else str(fetched_at)])
    raw = json.dumps(packed, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    return MAGIC + zlib.compress(raw, level=6)


def decode_block(payload):
    if not isinstance(payload, bytes) or not payload.startswith(MAGIC):
        raise ValueError('unknown compact ranking format')
    decompressor = zlib.decompressobj()
    raw = decompressor.decompress(payload[len(MAGIC):], 512_000)
    if not decompressor.eof or decompressor.unused_data or decompressor.unconsumed_tail:
        raise ValueError('invalid or oversized compact ranking payload')
    rows = json.loads(raw)
    if not isinstance(rows, list) or not 1 <= len(rows) <= BLOCK_SIZE:
        raise ValueError('invalid row count')
    for row in rows:
        if not isinstance(row, list) or len(row) != 6:
            raise ValueError('invalid row shape')
    return rows


def position_to_block(position):
    if not isinstance(position, int) or position < 1:
        raise ValueError('position must be positive')
    return divmod(position - 1, BLOCK_SIZE)
