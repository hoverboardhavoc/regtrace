"""Smoke tests for the vector YAML loader."""

import pytest
from pathlib import Path

from regtrace import vectors as vectors_mod


def test_first_vector_loads(tmp_path):
    v = vectors_mod.load(Path("vectors/timer/pwm_init_center_aligned_16khz.yaml"))
    assert v.vector_id == "timer_pwm_init_center_aligned_16khz"
    assert v.peripheral == "timer"
    assert v.name == "pwm_init_center_aligned_16khz"
    assert v.mode == "register_writes"
    assert set(v.implementations) == {"gd-spl/gd32f1x0", "libopencm3/stm32f0"}


def test_canonical_pair_auto_derived_for_two():
    v = vectors_mod.load(Path("vectors/timer/pwm_init_center_aligned_16khz.yaml"))
    pair = v.canonical_pair()
    assert set(pair) == {"gd-spl/gd32f1x0", "libopencm3/stm32f0"}


def _write(tmp_path, peri: str, name: str, body: str) -> Path:
    d = tmp_path / "vectors" / peri
    d.mkdir(parents=True)
    p = d / f"{name}.yaml"
    p.write_text(body)
    return p


def test_name_must_match_basename(tmp_path):
    p = _write(tmp_path, "timer", "myvec", """\
name: not_myvec
implementations:
  libopencm3/stm32f0:
    body: |
      x = 1;
""")
    with pytest.raises(ValueError, match="must equal the YAML basename"):
        vectors_mod.load(p)


def test_default_compare_required_for_three_or_more(tmp_path):
    p = _write(tmp_path, "timer", "x", """\
name: x
implementations:
  libopencm3/stm32f0:
    body: |
      x = 1;
  libopencm3/stm32f1:
    body: |
      x = 1;
  libopencm3/stm32f4:
    body: |
      x = 1;
""")
    with pytest.raises(ValueError, match="default_compare"):
        vectors_mod.load(p)


def test_assert_only_and_ignore_mutually_exclusive(tmp_path):
    p = _write(tmp_path, "timer", "x", """\
name: x
assert_only:
  - <TIM1_BASE>+0x00..0x44
ignore:
  - <RCU_BASE>+0x18
implementations:
  libopencm3/stm32f0:
    body: |
      x = 1;
""")
    with pytest.raises(ValueError, match="mutually exclusive"):
        vectors_mod.load(p)


def test_read_responses_normalised(tmp_path):
    p = _write(tmp_path, "adc", "calibration", """\
name: calibration
mode: with_polling
read_responses:
  "<ADC_BASE>+0x08": 0
  "<ADC_BASE>+0x10": [1, 1, 0]
implementations:
  libopencm3/stm32f0:
    body: |
      x = 1;
""")
    v = vectors_mod.load(p)
    assert v.read_responses["<ADC_BASE>+0x08"] == 0
    assert v.read_responses["<ADC_BASE>+0x10"] == [1, 1, 0]
