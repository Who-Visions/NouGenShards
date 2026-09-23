"""Operational decision cache. Keys already carry schema and backend version,
so an entry can never be reused across either. Not a shard store."""
from __future__ import annotations

from collections import OrderedDict
from typing import Optional

from .types import DecisionReceipt


class MemoryCache:
    def __init__(self, maxsize: int = 4096):
        self.maxsize = maxsize
        self._d: "OrderedDict[str, DecisionReceipt]" = OrderedDict()

    def get(self, key: str) -> Optional[DecisionReceipt]:
        r = self._d.get(key)
        if r is not None:
            self._d.move_to_end(key)
        return r

    def put(self, key: str, receipt: DecisionReceipt) -> None:
        self._d[key] = receipt
        self._d.move_to_end(key)
        while len(self._d) > self.maxsize:
            self._d.popitem(last=False)


class NullCache:
    def get(self, key: str) -> None:
        return None

    def put(self, key: str, receipt: DecisionReceipt) -> None:
        pass
