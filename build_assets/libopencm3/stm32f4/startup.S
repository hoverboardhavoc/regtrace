/* Minimal startup for STM32F4 (Cortex-M4 + FPU) snippet harness. */

    .syntax unified
    .cpu cortex-m4
    .fpu fpv4-sp-d16
    .thumb

    .section .vectors, "a", %progbits
    .align 2
    .global _vectors
_vectors:
    .word _estack
    .word _start + 1
    .word _default_handler + 1   /* NMI */
    .word _default_handler + 1   /* HardFault */
    .word _default_handler + 1   /* MemManage */
    .word _default_handler + 1   /* BusFault */
    .word _default_handler + 1   /* UsageFault */
    .word 0
    .word 0
    .word 0
    .word 0
    .word _default_handler + 1   /* SVCall */
    .word _default_handler + 1   /* DebugMon */
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
    ldr  r0, =_sentinel + 1
    mov  lr, r0
    bl   regtrace_test
    b    _sentinel

    .section .text._sentinel, "ax", %progbits
    .thumb_func
    .global _sentinel
_sentinel:
    bkpt #0x55
