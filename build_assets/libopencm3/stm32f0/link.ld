/* Minimal linker script for STM32F0 snippet harness.
 *
 * Memory map matches STM32F030R8 (64 KiB Flash @ 0x08000000, 8 KiB SRAM @
 * 0x20000000) — generous enough for any v0.1 snippet. Real-target memory
 * sizes are irrelevant: Unicorn maps whatever ranges we declare.
 */

ENTRY(_start)

MEMORY
{
    FLASH (rx) : ORIGIN = 0x08000000, LENGTH = 64K
    SRAM  (rwx): ORIGIN = 0x20000000, LENGTH = 8K
}

_estack = ORIGIN(SRAM) + LENGTH(SRAM);

SECTIONS
{
    .vectors : {
        KEEP(*(.vectors))
    } > FLASH

    .text : {
        *(.text*)
        *(.rodata*)
    } > FLASH

    .data : {
        _sdata = .;
        *(.data*)
        _edata = .;
    } > SRAM AT > FLASH

    .bss : {
        _sbss = .;
        *(.bss*)
        *(COMMON)
        _ebss = .;
    } > SRAM

    /DISCARD/ : {
        *(.ARM.exidx*)
        *(.ARM.attributes)
    }
}
