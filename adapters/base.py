"""
Source adapter interface.

An adapter fetches items from one source (a fixture file, a live API) and
returns them as SourceItem records. It does nothing else: no scoring, no
extraction, no judgment. Everything downstream sees the same record shape,
whichever adapter produced it.

source_id is an item's identity everywhere downstream. It is namespaced by
adapter ("fixture:fx-1001") and always compared as an exact string, never by
substring, so "fixture:fx-1001" can never be mistaken for "fixture:fx-10010".

Fields a source leaves out stay None. An adapter never fills them in.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceItem:
    source_id: str              # "<adapter>:<native id>", compared exactly
    title: str
    date: str                   # YYYY-MM-DD
    body: str
    region: str | None = None   # None: the source did not say
    unit: str | None = None
    url: str | None = None


def source_id(adapter_name, native_id):
    return f"{adapter_name}:{native_id}"


class SourceAdapter(ABC):
    name = ""   # namespace for source_id
    mode = ""   # "fixture" (offline) or "live" (network)

    @abstractmethod
    def collect(self, queries=()):
        """Return a list of SourceItem. `queries` are the run's approved queries."""
