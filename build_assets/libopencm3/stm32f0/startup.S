/* Minimal startup for STM32F0 (Cortex-M0) snippet harness.
 *
 * Layout:
 *   - Initial SP at top of SRAM (set in linker script)
 *   - Reset vector → _start
 *   - _start sets LR to the bkpt sentinel address, branches to regtrace_test
 *   - On return from regtrace_test, execution falls into the bkpt at the LR
 *     sentinel; Unicorn halts cleanly.
 *
 * Other Cortex-M0 exception vectors point at a self-loop default handler so a
 * fault in the test snippet is observable but doesn't crash the emulator.
 */

    .syntax unified
    .cpu cortex-m0
    .thumb

    .section .vectors, "a", %progbits
    .align 2
    .global _vectors
_vectors:
    .word _estack                /* Initial SP */
    .word _start + 1             /* Reset_Handler — Thumb bit set */
    .word _default_handler + 1   /* NMI */
    .word _default_handler + 1   /* HardFault */
    .word 0
    .word 0
    .word 0
    .word 0
    .word 0
    .word 0
    .word 0
    .word _default_handler + 1   /* SVCall */
    .word 0
    .word 0
    .word _default_handler + 1   /* PendSV */
    .word _default_handler + 1   /* SysTick */

    .section .text._default_handler, "ax", %progbits
    .thumb_func
    .global _default_handler
_default_handler:
    b _default_handler

    .section .text._start, "ax", %progbits
    .thumb_func
    .global _start
_start:
    ldr  r0, =_sentinel + 1    /* Thumb-mode address of bkpt */
    mov  lr, r0
    bl   regtrace_test
    /* Fallthrough — should never reach. */
    b    _sentinel

    .section .text._sentinel, "ax", %progbits
    .thumb_func
    .global _sentinel
_sentinel:
    bkpt #0x55                 /* Unicorn halts on this with UC_ERR_EXCEPTION */
