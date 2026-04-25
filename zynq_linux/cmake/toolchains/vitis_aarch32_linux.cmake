set(CMAKE_SYSTEM_NAME Linux)
set(CMAKE_SYSTEM_PROCESSOR arm)

set(VITIS_ARM_GNU_ROOT "F:/Xilinx/Vitis/2020.2/gnu/aarch32/nt/gcc-arm-linux-gnueabi" CACHE PATH "Vitis ARM Linux toolchain root")
set(CMAKE_C_COMPILER "${VITIS_ARM_GNU_ROOT}/bin/arm-linux-gnueabihf-gcc.exe")
set(CMAKE_CXX_COMPILER "${VITIS_ARM_GNU_ROOT}/bin/arm-linux-gnueabihf-g++.exe")

set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
