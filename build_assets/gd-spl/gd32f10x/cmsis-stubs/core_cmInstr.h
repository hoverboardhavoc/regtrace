/* Minimal CMSIS-Core 4.x compatibility shim for GD's core_cm3.h.
 *
 * GD32 CMSIS ships only core_cm3.h; it expects CMSIS-Core 4.x to provide the
 * split-out instruction/function headers. Real silicon would call these (NOP,
 * WFI, DSB, etc.) at runtime; for snippet emulation we just need the symbols
 * to compile.
 *
 * License: this file is regtrace's own (MPL-2.0). Provides only declarations
 * and trivial inline wrappers around standard GCC intrinsics — no copyrightable
 * content from ARM's CMSIS.
 */

#ifndef __CORE_CMINSTR_H
#define __CORE_CMINSTR_H

#include <stdint.h>

#define __NOP()         __asm volatile ("nop")
#define __WFI()         __asm volatile ("wfi")
#define __WFE()         __asm volatile ("wfe")
#define __SEV()         __asm volatile ("sev")
#define __ISB()         __asm volatile ("isb 0xF":::"memory")
#define __DSB()         __asm volatile ("dsb 0xF":::"memory")
#define __DMB()         __asm volatile ("dmb 0xF":::"memory")
#define __CLREX()       __asm volatile ("clrex" ::: "memory")

#define __REV(v)        __builtin_bswap32(v)
#define __REV16(v)      __builtin_bswap16(v)
#define __REVSH(v)      ((int16_t)__builtin_bswap16(v))

static inline __attribute__((always_inline)) uint32_t __RBIT(uint32_t v) {
    uint32_t r;
    __asm volatile ("rbit %0, %1" : "=r"(r) : "r"(v));
    return r;
}

#define __LDREXB(p)     __builtin_arm_ldrex(p)
#define __LDREXH(p)     __builtin_arm_ldrex(p)
#define __LDREXW(p)     __builtin_arm_ldrex(p)
#define __STREXB(v, p)  __builtin_arm_strex(v, p)
#define __STREXH(v, p)  __builtin_arm_strex(v, p)
#define __STREXW(v, p)  __builtin_arm_strex(v, p)

#endif /* __CORE_CMINSTR_H */
