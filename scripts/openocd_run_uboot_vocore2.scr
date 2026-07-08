targets
reg pc
mdw 0xb0000010
mdw 0x10000000
cpu_pll_init
adapter speed 1000
dram_init 128
mt7628.cpu0 configure -work-area-phys 0xa0001000 -work-area-size 4096 -work-area-backup 0
mww 0xa0000000 0xdeadbeef
mdw 0xa0000000
load_image u-boot/u-boot.bin 0x80200000 bin
reg pc 0x80200000
resume
