"""Smoke tests for the targets/ TOML loader."""

from regtrace import targets


def test_stm32f0_loads_and_symbolises():
    t = targets.load("stm32f0")
    assert t.arch == "cortex-m0"
    assert t.unicorn_arch == "arm"
    assert t.unicorn_mode == "thumb"
    assert t.peripheral_bases["TIM1_BASE"] == 0x40012C00
    assert t.symbolise(0x40012C00) == "<TIM1_BASE>+0x00"
    assert t.symbolise(0x40012C2C) == "<TIM1_BASE>+0x2C"


def test_stm32f0_peripheral_filter():
    t = targets.load("stm32f0")
    assert t.is_peripheral(0x40012C00)        # TIM1
    assert t.is_peripheral(0xE000ED00)        # SCB
    assert not t.is_peripheral(0x20000000)    # SRAM
    assert not t.is_peripheral(0x08000000)    # Flash


def test_stm32f0_reset_values_present():
    t = targets.load("stm32f0")
    assert t.reset_values["RCC_BASE"][0x00] == 0x83
