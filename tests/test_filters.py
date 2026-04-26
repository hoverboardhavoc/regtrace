"""Tests for assert_only / ignore filtering in the comparator."""

from regtrace.compare.engine import (
    TraceLine, _line_matches_range, _parse_range, apply_filters, compare,
)


def _w(addr_str: str, value: int = 0, size: int = 4) -> TraceLine:
    return TraceLine(op="W", size=size, address_str=addr_str, value=value)


def test_parse_single_offset():
    sym, lo, hi = _parse_range("<TIM1_BASE>+0x14")
    assert (sym, lo, hi) == ("TIM1_BASE", 0x14, 0x14)


def test_parse_range():
    sym, lo, hi = _parse_range("<TIM1_BASE>+0x00..0x44")
    assert (sym, lo, hi) == ("TIM1_BASE", 0x00, 0x44)


def test_parse_no_offset_means_anything():
    sym, lo, hi = _parse_range("<RCC_BASE>")
    assert sym == "RCC_BASE"
    assert lo == 0 and hi == 0xFFFFFFFF


def test_match_within_range():
    line = _w("<TIM1_BASE>+0x14")
    assert _line_matches_range(line, "TIM1_BASE", 0x00, 0x44)
    assert not _line_matches_range(line, "TIM1_BASE", 0x20, 0x44)
    assert not _line_matches_range(line, "RCC_BASE", 0x00, 0x44)


def test_assert_only_keeps_matches():
    lines = [
        _w("<TIM1_BASE>+0x00"),
        _w("<RCC_BASE>+0x18"),
        _w("<TIM1_BASE>+0x14"),
    ]
    out = apply_filters(lines, assert_only=("<TIM1_BASE>+0x00..0x44",))
    assert [l.address_str for l in out] == ["<TIM1_BASE>+0x00", "<TIM1_BASE>+0x14"]


def test_ignore_drops_matches():
    lines = [
        _w("<TIM1_BASE>+0x00"),
        _w("<RCC_BASE>+0x18"),
        _w("<TIM1_BASE>+0x14"),
    ]
    out = apply_filters(lines, ignore=("<RCC_BASE>+0x18",))
    assert [l.address_str for l in out] == ["<TIM1_BASE>+0x00", "<TIM1_BASE>+0x14"]


def test_ignore_whole_symbol():
    lines = [
        _w("<TIM1_BASE>+0x00"),
        _w("<RCC_BASE>+0x18"),
        _w("<RCC_BASE>+0x14"),
    ]
    out = apply_filters(lines, ignore=("<RCC_BASE>",))
    assert [l.address_str for l in out] == ["<TIM1_BASE>+0x00"]


def test_filter_then_compare_ignores_clock_enables():
    a = [
        _w("<RCC_BASE>+0x18", 0x800),    # APB2ENR — TIM1 clock
        _w("<TIM1_BASE>+0x00", 0x60),
    ]
    b = [
        _w("<RCC_BASE>+0x18", 0x801),    # vendor enables a different bit too
        _w("<TIM1_BASE>+0x00", 0x60),
    ]
    a2 = apply_filters(a, ignore=("<RCC_BASE>",))
    b2 = apply_filters(b, ignore=("<RCC_BASE>",))
    cr = compare("register_writes", a2, "a", b2, "b")
    assert cr.matched
