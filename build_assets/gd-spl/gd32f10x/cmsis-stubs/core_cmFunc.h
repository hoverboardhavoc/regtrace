/* Minimal CMSIS-Core 4.x compatibility shim for GD's core_cm3.h.
 *
 * Provides core-register accessors as trivial inline asm. Same rationale as
 * core_cmInstr.h.
 *
 * License: regtrace's own (MPL-2.0). No copyrightable content from ARM's CMSIS.
 */

#ifndef __CORE_CMFUNC_H
#define __CORE_CMFUNC_H

#include <stdint.h>

static inline __attribute__((always_inline)) uint32_t __get_CONTROL(void) {
    uint32_t r; __asm volatile ("mrs %0, control" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) void __set_CONTROL(uint32_t v) {
    __asm volatile ("msr control, %0" :: "r"(v) : "memory");
}
static inline __attribute__((always_inline)) uint32_t __get_IPSR(void) {
    uint32_t r; __asm volatile ("mrs %0, ipsr" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) uint32_t __get_APSR(void) {
    uint32_t r; __asm volatile ("mrs %0, apsr" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) uint32_t __get_xPSR(void) {
    uint32_t r; __asm volatile ("mrs %0, xpsr" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) uint32_t __get_PSP(void) {
    uint32_t r; __asm volatile ("mrs %0, psp" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) void __set_PSP(uint32_t v) {
    __asm volatile ("msr psp, %0" :: "r"(v));
}
static inline __attribute__((always_inline)) uint32_t __get_MSP(void) {
    uint32_t r; __asm volatile ("mrs %0, msp" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) void __set_MSP(uint32_t v) {
    __asm volatile ("msr msp, %0" :: "r"(v));
}
static inline __attribute__((always_inline)) uint32_t __get_PRIMASK(void) {
    uint32_t r; __asm volatile ("mrs %0, primask" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) void __set_PRIMASK(uint32_t v) {
    __asm volatile ("msr primask, %0" :: "r"(v) : "memory");
}
static inline __attribute__((always_inline)) void __enable_irq(void)  { __asm volatile ("cpsie i" ::: "memory"); }
static inline __attribute__((always_inline)) void __disable_irq(void) { __asm volatile ("cpsid i" ::: "memory"); }
static inline __attribute__((always_inline)) uint32_t __get_BASEPRI(void) {
    uint32_t r; __asm volatile ("mrs %0, basepri" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) void __set_BASEPRI(uint32_t v) {
    __asm volatile ("msr basepri, %0" :: "r"(v) : "memory");
}
static inline __attribute__((always_inline)) uint32_t __get_FAULTMASK(void) {
    uint32_t r; __asm volatile ("mrs %0, faultmask" : "=r"(r)); return r;
}
static inline __attribute__((always_inline)) void __set_FAULTMASK(uint32_t v) {
    __asm volatile ("msr faultmask, %0" :: "r"(v) : "memory");
}

#endif /* __CORE_CMFUNC_H */
