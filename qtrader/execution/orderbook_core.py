from __future__ import annotations

from typing import Any


def _import_core() -> Any:
    try:
        import qtrader_core  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            "Missing native extension `qtrader_core`. Build/install it with `make rust-py-dev` "
            "(requires maturin + Rust toolchain)."
        ) from e
    return qtrader_core


_core = _import_core()

OrderbookEngine = _core.OrderbookEngine
MatchingEngine = _core.MatchingEngine
rust_version = _core.rust_version

