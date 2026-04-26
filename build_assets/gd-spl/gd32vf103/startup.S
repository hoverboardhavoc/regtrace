/* Minimal startup for GD32VF103 (RV32IMAC, Nuclei N200) snippet harness.
 *
 * Same shape as the Cortex-M startups: set SP, branch to regtrace_test
 * with RA pointing at the EBREAK sentinel, halt cleanly on return.
 *
 * RISC-V calling convention: a0-a7 are arg/return registers, ra (x1) is
 * the return address. We set ra = _sentinel before calling regtrace_test
 * so the function's `ret` (= jalr x0, ra, 0) jumps to the EBREAK.
 */

    .section .text._start, "ax", %progbits
    .global _start
    .type _start, @function
_start:
    /* Initialise the stack pointer. _estack comes from the linker script. */
    la    sp, _estack
    /* Set return address to the EBREAK sentinel. */
    la    ra, _sentinel
    /* Branch to the test function. */
    call  regtrace_test
    /* Fallthrough — should never reach. */
    j     _sentinel

    .section .text._sentinel, "ax", %progbits
    .global _sentinel
    .type _sentinel, @function
_sentinel:
    ebreak
    /* If somehow execution survives ebreak, loop. */
    j     _sentinel
