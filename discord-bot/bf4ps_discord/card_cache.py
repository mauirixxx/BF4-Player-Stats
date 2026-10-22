"""Bounded, single-flight PNG rendering cache for the active Discord leader."""
import asyncio
import hashlib
import json
import logging
import time
from collections import OrderedDict

log = logging.getLogger("bf4ps.discord.card_cache")


class BusyError(Exception):
    pass


class CardCache:
    def __init__(self, *, max_bytes=96 * 1024 * 1024, max_items=120,
                 ttl=900, concurrency=2, max_pending=40):
        self._items = OrderedDict()
        self._bytes = 0
        self._max_bytes = max_bytes
        self._max_items = max_items
        self._ttl = ttl
        self._sem = asyncio.Semaphore(concurrency)
        self._max_pending = max_pending
        self._pending = {}
        self._lock = asyncio.Lock()
        self._hits = self._misses = self._busy = 0

    @staticmethod
    def key(*parts):
        payload = json.dumps(parts, sort_keys=True, default=str, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    async def get_or_render(self, key, factory):
        """factory is an async callable that fetches artwork and renders a PNG.

        One task per key, with a bounded total pending queue. Cancellation of
        one Discord interaction does not cancel the shared render.
        """
        async with self._lock:
            entry = self._items.get(key)
            if entry:
                data, expiry = entry
                if expiry > time.monotonic():
                    self._items.move_to_end(key)
                    self._hits += 1
                    return data
                self._bytes -= len(data)
                del self._items[key]
            task = self._pending.get(key)
            if task is None:
                if len(self._pending) >= self._max_pending:
                    self._busy += 1
                    raise BusyError("Image render queue is full")
                self._misses += 1
                task = asyncio.create_task(self._produce(key, factory))
                self._pending[key] = task
        return await asyncio.shield(task)

    async def _produce(self, key, factory):
        try:
            async with self._sem:
                data = await factory()
            if not isinstance(data, bytes):
                raise TypeError("Renderer did not return PNG bytes")
            async with self._lock:
                if len(data) <= self._max_bytes:
                    previous = self._items.pop(key, None)
                    if previous:
                        self._bytes -= len(previous[0])
                    self._items[key] = (data, time.monotonic() + self._ttl)
                    self._bytes += len(data)
                    while len(self._items) > self._max_items or self._bytes > self._max_bytes:
                        _, removed = self._items.popitem(last=False)
                        self._bytes -= len(removed[0])
            return data
        finally:
            async with self._lock:
                self._pending.pop(key, None)
                total = self._hits + self._misses
                if total and total % 25 == 0:
                    log.info("card_cache hits=%d misses=%d busy=%d pending=%d items=%d bytes=%d",
                             self._hits, self._misses, self._busy,
                             len(self._pending), len(self._items), self._bytes)
