"""targets/<family>.toml loader.

A target file declares per-chip-family peripheral memory layout used both to
symbolise raw addresses in trace output and to filter "is this address a
peripheral write?" during extraction.

Schema:
  arch                 = "cortex-m0" | "cortex-m3" | "cortex-m4" | ...
  unicorn_arch         = "arm"
  unicorn_mode         = "thumb"
  peripheral_ranges    = list of {start, end} pairs (inclusive of start,
                         inclusive of end) — peripheral MMIO address space.
  peripheral_bases     = { SYMBOL: 0xADDR, ... }
  register_names       = { SYMBOL: { 0xOFFSET: "REGNAME" } } (optional, for trace comments)
  reset_values         = { SYMBOL: { 0xOFFSET: 0xVALUE } } (optional)
  bit_band_aliases     = { 0xALIAS_BASE: 0xUNDERLYING_BASE } (Cortex-M3 only)
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .paths import targets_dir


@dataclass(frozen=True)
class AddressRange:
    start: int
    end: int  # inclusive

    def contains(self, addr: int) -> bool:
        return self.start <= addr <= self.end


@dataclass(frozen=True)
class Target:
    name: str
    arch: str
    unicorn_arch: str
    unicorn_mode: str
    peripheral_ranges: tuple[AddressRange, ...]
    peripheral_bases: dict[str, int] = field(default_factory=dict)
    register_names: dict[str, dict[int, str]] = field(default_factory=dict)
    reset_values: dict[str, dict[int, int]] = field(default_factory=dict)
    bit_band_aliases: dict[int, int] = field(default_factory=dict)

    def is_peripheral(self, addr: int) -> bool:
        return any(r.contains(addr) for r in self.peripheral_ranges)

    def symbolise(self, addr: int) -> str:
        """Return `<SYMBOL>+0xOFFSET` for a peripheral address, or hex if no base matches."""
        # Pick the base with the largest address ≤ addr (longest-match).
        best_name: str | None = None
        best_base: int = 0
        for name, base in self.peripheral_bases.items():
            if base <= addr and base > best_base:
                best_name = name
                best_base = base
        if best_name is None:
            return f"0x{addr:08X}"
        return f"<{best_name}>+0x{addr - best_base:02X}"


def load(name: str) -> Target:
    """Load targets/<name>.toml."""
    path = targets_dir() / f"{name}.toml"
    with open(path, "rb") as f:
        raw = tomllib.load(f)
    ranges = tuple(
        AddressRange(start=int(r["start"], 0) if isinstance(r["start"], str) else r["start"],
                     end=int(r["end"], 0) if isinstance(r["end"], str) else r["end"])
        for r in raw["peripheral_ranges"]
    )
    bases = {k: _to_int(v) for k, v in raw.get("peripheral_bases", {}).items()}
    reg_names = {k: {_to_int(off): nm for off, nm in v.items()}
                 for k, v in raw.get("register_names", {}).items()}
    reset = {k: {_to_int(off): _to_int(val) for off, val in v.items()}
             for k, v in raw.get("reset_values", {}).items()}
    bit_band = {_to_int(k): _to_int(v) for k, v in raw.get("bit_band_aliases", {}).items()}
    return Target(
        name=name,
        arch=raw["arch"],
        unicorn_arch=raw["unicorn_arch"],
        unicorn_mode=raw["unicorn_mode"],
        peripheral_ranges=ranges,
        peripheral_bases=bases,
        register_names=reg_names,
        reset_values=reset,
        bit_band_aliases=bit_band,
    )


def _to_int(v: int | str) -> int:
    return int(v, 0) if isinstance(v, str) else int(v)
