"""Pure codec checks; no production DB required."""
import importlib.util
from pathlib import Path

import pytest

path = Path(__file__).resolve().parents[1] / 'bf4ps' / 'compact_rank_codec.py'
spec = importlib.util.spec_from_file_location('compact_rank_codec', path)
codec = importlib.util.module_from_spec(spec)
spec.loader.exec_module(codec)


def test_round_trip_precision_and_nulls():
    rows = [(42, 1, 123, '2.123456789123456789', None, '2026-10-31T12:34:56+00:00'),
            (99, 1, 123, None, '49.999999999', None)]
    assert codec.decode_block(codec.encode_block(rows)) == [
        [42, 1, 123, '2.123456789123456789', None, '2026-10-31T12:34:56+00:00'],
        [99, 1, 123, None, '49.999999999', None]]


def test_full_block_and_positions():
    rows = [(i, i, i, '1.0', '2.0', None) for i in range(1, 1001)]
    assert len(codec.decode_block(codec.encode_block(rows))) == 1000
    assert codec.position_to_block(1) == (0, 0)
    assert codec.position_to_block(1001) == (1, 0)


@pytest.mark.parametrize('rows', [[], [(0, 1, 2, None, None, None)],
                                  [(1, 1, 2, None, None, None)] * 2])
def test_reject_bad_rows(rows):
    with pytest.raises(ValueError):
        codec.encode_block(rows)


def test_reject_bad_payload():
    with pytest.raises(ValueError):
        codec.decode_block(b'bad')


def test_reject_trailing_data_and_oversize():
    import zlib
    valid = codec.encode_block([(1, 1, 1, None, None, None)])
    with pytest.raises(ValueError):
        codec.decode_block(valid + b'junk')
    oversize = codec.MAGIC + zlib.compress(b'x' * 512_001)
    with pytest.raises(ValueError):
        codec.decode_block(oversize)
