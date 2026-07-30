"""Plugin SDK — register custom SourceAdapter implementations."""

from __future__ import annotations

from typing import Type

from sources.base import SourceAdapter

_REGISTRY: dict[str, Type[SourceAdapter]] = {}


def register_source(name: str, adapter_cls: Type[SourceAdapter]) -> None:
    _REGISTRY[name] = adapter_cls


def get_plugin(name: str) -> Type[SourceAdapter] | None:
    return _REGISTRY.get(name)


def list_plugins() -> list[str]:
    return sorted(_REGISTRY.keys())
