/* Minimal gd32f1x0_libopt.h — selects which SPL peripheral headers get
 * pulled in via gd32f1x0.h. Vendor SPL expects the user to provide this; we
 * just include everything so vectors can use any peripheral.
 */

#ifndef GD32F1X0_LIBOPT_H
#define GD32F1X0_LIBOPT_H

#include "gd32f1x0_rcu.h"
#include "gd32f1x0_adc.h"
#include "gd32f1x0_crc.h"
#include "gd32f1x0_dbg.h"
#include "gd32f1x0_dma.h"
#include "gd32f1x0_exti.h"
#include "gd32f1x0_fmc.h"
#include "gd32f1x0_gpio.h"
#include "gd32f1x0_syscfg.h"
#include "gd32f1x0_i2c.h"
#include "gd32f1x0_fwdgt.h"
#include "gd32f1x0_pmu.h"
#include "gd32f1x0_rtc.h"
#include "gd32f1x0_spi.h"
#include "gd32f1x0_timer.h"
#include "gd32f1x0_usart.h"
#include "gd32f1x0_wwdgt.h"
#include "gd32f1x0_misc.h"

#endif
