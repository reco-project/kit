/* Stub for L4T 36.5 / kernel 5.15.185-tegra
 * .remove returns int (pre-Linux 6.1)
 * .probe has i2c_device_id arg (pre-Linux 6.3)
 */
#ifndef _NVIDIA_CONFTEST_H_
#define _NVIDIA_CONFTEST_H_
#define NV_I2C_DRIVER_STRUCT_REMOVE_RETURN_TYPE_INT 1
/* NV_I2C_DRIVER_STRUCT_PROBE_WITHOUT_I2C_DEVICE_ID_ARG not defined - 5.15 keeps id arg */
#endif
