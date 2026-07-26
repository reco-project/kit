obj-m := nv_imx477.o
KDIR := /lib/modules/$(shell uname -r)/build
NVIDIA_OOT := /usr/src/nvidia/nvidia-oot
KBUILD_EXTRA_SYMBOLS := $(NVIDIA_OOT)/Module.symvers
ccflags-y += -I$(NVIDIA_OOT)/include
ccflags-y += -Wno-error
all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) KBUILD_EXTRA_SYMBOLS=$(NVIDIA_OOT)/Module.symvers modules
clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
