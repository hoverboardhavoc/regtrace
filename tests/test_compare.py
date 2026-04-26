"""Smoke tests for the compare engine."""

from regtrace.compare.engine import TraceLine, compare


def _w(addr_str: str, value: int, size: int = 4) -> TraceLine:
    return TraceLine(op="W", size=size, address_str=addr_str, value=value)


def _r(addr_str: str, value: int, size: int = 4) -> TraceLine:
    return TraceLine(op="R", size=size, address_str=addr_str, value=value)


def test_register_writes_match():
    a = [_w("<TIM1_BASE>+0x00", 0x80), _w("<TIM1_BASE>+0x2C", 0x8CA)]
    b = [_w("<TIM1_BASE>+0x00", 0x80), _w("<TIM1_BASE>+0x2C", 0x8CA)]
    cr = compare("register_writes", a, "a", b, "b")
    assert cr.matched
    assert cr.diff == []


def test_register_writes_diff():
    a = [_w("<TIM1_BASE>+0x00", 0x80)]
    b = [_w("<TIM1_BASE>+0x00", 0xC0)]
    cr = compare("register_writes", a, "a", b, "b")
    assert not cr.matched
    assert len(cr.diff) == 1


def test_width_strict():
    """W4 to addr X must NOT compare equal to W2+W2 covering same bytes."""
    a = [_w("<TIM1_BASE>+0x00", 0x80, size=4)]
    b = [_w("<TIM1_BASE>+0x00", 0x80, size=2), _w("<TIM1_BASE>+0x02", 0x00, size=2)]
    cr = compare("register_writes", a, "a", b, "b")
    assert not cr.matched


def test_register_writes_ignores_reads():
    a = [_r("<TIM1_BASE>+0x10", 0), _w("<TIM1_BASE>+0x00", 0x80)]
    b = [_w("<TIM1_BASE>+0x00", 0x80), _r("<TIM1_BASE>+0x10", 1)]
    cr = compare("register_writes", a, "a", b, "b")
    assert cr.matched


def test_with_polling_includes_reads():
    a = [_r("<ADC_BASE>+0x10", 1), _w("<ADC_BASE>+0x00", 0x1)]
    b = [_w("<ADC_BASE>+0x00", 0x1), _r("<ADC_BASE>+0x10", 1)]
    cr = compare("with_polling", a, "a", b, "b")
    assert not cr.matched  # different order


def test_final_state_unordered():
    a = [_w("<TIM1_BASE>+0x00", 0x80), _w("<TIM1_BASE>+0x2C", 0x8CA)]
    b = [_w("<TIM1_BASE>+0x2C", 0x8CA), _w("<TIM1_BASE>+0x00", 0x80)]
    cr = compare("final_state", a, "a", b, "b")
    assert cr.matched
