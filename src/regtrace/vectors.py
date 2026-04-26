"""Vector YAML loader + schema validation.

A vector is a self-contained snippet (one C function per implementation) plus
the metadata needed to compile, trace, and compare it.

Schema (v0.1):
  name           : str (required, must equal the YAML basename)
  description    : str (optional, free-form)
  mode           : "register_writes" | "final_state" | "with_polling"
                   (default: "register_writes")
  default_compare: [impl-slug, impl-slug] (required when len(implementations) >= 3;
                   auto-derived when exactly 2)
  read_responses : { "<BASE>+0xOFFSET": int | [int, ...] } (optional, v0.2+)
  assert_only    : ["<BASE>+0xOFFSET..0xOFFSET", ...] (optional, v0.2+)
  ignore         : ["<BASE>+0xOFFSET", ...] (optional, v0.2+)
  implementations: { "<library>/<target>": { includes: [str], body: str } }

The implementation key encodes both library-id (e.g. gd-spl) and target-id
(e.g. gd32f1x0). Both are required because the same library may produce
different traces for different targets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .paths import vectors_dir


VALID_MODES = {"register_writes", "final_state", "with_polling"}


@dataclass(frozen=True)
class Implementation:
    library: str        # e.g. "gd-spl"
    target: str         # e.g. "gd32f1x0"
    includes: tuple[str, ...]
    body: str

    @property
    def slug(self) -> str:
        return f"{self.library}/{self.target}"


@dataclass(frozen=True)
class Vector:
    yaml_path: Path
    peripheral: str          # parent dir under vectors/
    name: str                # YAML basename and `name:` field (must match)
    description: str
    mode: str
    default_compare: tuple[str, str] | None
    implementations: dict[str, Implementation]
    read_responses: dict[str, int | list[int]] = field(default_factory=dict)
    assert_only: tuple[str, ...] = field(default_factory=tuple)
    ignore: tuple[str, ...] = field(default_factory=tuple)

    @property
    def vector_id(self) -> str:
        """Canonical identifier: `<peripheral>_<name>`."""
        return f"{self.peripheral}_{self.name}"

    def canonical_pair(self) -> tuple[str, str]:
        if self.default_compare is not None:
            return self.default_compare
        if len(self.implementations) == 2:
            slugs = list(self.implementations.keys())
            return (slugs[0], slugs[1])
        raise ValueError(
            f"vector {self.vector_id}: cannot derive canonical pair — "
            f"{len(self.implementations)} implementations declared and no default_compare set"
        )


def load(yaml_path: Path) -> Vector:
    """Load and validate a vector YAML."""
    yaml_path = yaml_path.resolve()
    with open(yaml_path) as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{yaml_path}: top-level YAML must be a mapping")

    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ValueError(f"{yaml_path}: missing or empty `name:` field")
    if name != yaml_path.stem:
        raise ValueError(
            f"{yaml_path}: `name: {name}` must equal the YAML basename "
            f"`{yaml_path.stem}` (per pinned naming convention)"
        )

    peripheral = yaml_path.parent.name
    description = raw.get("description", "")
    mode = raw.get("mode", "register_writes")
    if mode not in VALID_MODES:
        raise ValueError(f"{yaml_path}: mode={mode!r} not in {sorted(VALID_MODES)}")

    impls_raw = raw.get("implementations") or {}
    if not isinstance(impls_raw, dict) or not impls_raw:
        raise ValueError(f"{yaml_path}: `implementations:` must be a non-empty mapping")
    impls: dict[str, Implementation] = {}
    for slug, body in impls_raw.items():
        if "/" not in slug:
            raise ValueError(f"{yaml_path}: implementation key {slug!r} must be `<library>/<target>`")
        library, target = slug.split("/", 1)
        includes = tuple(body.get("includes", []) or [])
        impl_body = body.get("body", "")
        if not isinstance(impl_body, str) or not impl_body.strip():
            raise ValueError(f"{yaml_path}: implementation {slug!r} has empty body")
        impls[slug] = Implementation(
            library=library, target=target,
            includes=includes, body=impl_body,
        )

    default_compare_raw = raw.get("default_compare")
    default_compare: tuple[str, str] | None = None
    if default_compare_raw is not None:
        if not (isinstance(default_compare_raw, list) and len(default_compare_raw) == 2):
            raise ValueError(f"{yaml_path}: `default_compare:` must be a 2-element list")
        a, b = default_compare_raw
        if a not in impls or b not in impls:
            raise ValueError(
                f"{yaml_path}: default_compare entries {a!r}/{b!r} must be declared in implementations"
            )
        default_compare = (a, b)
    elif len(impls) >= 3:
        raise ValueError(
            f"{yaml_path}: {len(impls)} implementations declared — `default_compare:` is required"
        )

    read_responses_raw = raw.get("read_responses") or {}
    if not isinstance(read_responses_raw, dict):
        raise ValueError(f"{yaml_path}: `read_responses:` must be a mapping")
    read_responses: dict[str, int | list[int]] = {}
    for k, v in read_responses_raw.items():
        if isinstance(v, list):
            read_responses[k] = [int(x) for x in v]
        else:
            read_responses[k] = int(v)

    assert_only = tuple(raw.get("assert_only") or [])
    ignore = tuple(raw.get("ignore") or [])
    if assert_only and ignore:
        raise ValueError(f"{yaml_path}: `assert_only:` and `ignore:` are mutually exclusive")

    return Vector(
        yaml_path=yaml_path,
        peripheral=peripheral,
        name=name,
        description=description,
        mode=mode,
        default_compare=default_compare,
        implementations=impls,
        read_responses=read_responses,
        assert_only=assert_only,
        ignore=ignore,
    )


def discover(path: Path) -> list[Vector]:
    """Return all vectors under PATH (file or directory)."""
    path = path.resolve()
    if path.is_file():
        return [load(path)]
    if path.is_dir():
        results = [load(p) for p in sorted(path.rglob("*.yaml"))]
        return results
    raise FileNotFoundError(path)
