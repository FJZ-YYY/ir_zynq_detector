cmake_minimum_required(VERSION 3.20)

project(irdet_linux_ncnn_app LANGUAGES C CXX)

set(CMAKE_C_STANDARD 99)
set(CMAKE_C_STANDARD_REQUIRED ON)
set(CMAKE_CXX_STANDARD 11)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(IRDET_REPO_ROOT "${CMAKE_CURRENT_LIST_DIR}/.." CACHE PATH "Repository root")
set(IRDET_NCNN_INCLUDE_DIRS "" CACHE STRING "Semicolon-separated ncnn include directories")
set(IRDET_NCNN_LIBRARY "" CACHE FILEPATH "Path to libncnn.a or ncnn import library")

if(IRDET_NCNN_INCLUDE_DIRS STREQUAL "")
    message(FATAL_ERROR "Set IRDET_NCNN_INCLUDE_DIRS to the ncnn include directories.")
endif()
if(IRDET_NCNN_LIBRARY STREQUAL "" OR NOT EXISTS "${IRDET_NCNN_LIBRARY}")
    message(FATAL_ERROR "Set IRDET_NCNN_LIBRARY to the built ncnn library file.")
endif()

set(IRDET_ZYNQ_PS_INCLUDE "${IRDET_REPO_ROOT}/zynq_ps/include")
set(IRDET_ZYNQ_PS_SRC "${IRDET_REPO_ROOT}/zynq_ps/src")

set(IRDET_LINUX_NCNN_APP_SOURCES
    "${CMAKE_CURRENT_LIST_DIR}/src/irdet_linux_dw3x3_case.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/src/irdet_linux_main.cpp"
    "${CMAKE_CURRENT_LIST_DIR}/src/irdet_linux_ncnn_detector.cpp"
    "${IRDET_ZYNQ_PS_SRC}/ir_image_preprocess.c"
    "${IRDET_ZYNQ_PS_SRC}/ir_ssd_postprocess.c"
    "${IRDET_ZYNQ_PS_SRC}/ir_pl_dw3x3_full.c"
)

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    list(APPEND IRDET_LINUX_NCNN_APP_SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/src/irdet_linux_pl_dw3x3_probe.cpp"
    )
else()
    list(APPEND IRDET_LINUX_NCNN_APP_SOURCES
        "${CMAKE_CURRENT_LIST_DIR}/src/irdet_linux_pl_dw3x3_probe_stub.cpp"
    )
endif()

add_executable(irdet_linux_ncnn_app
    ${IRDET_LINUX_NCNN_APP_SOURCES}
)

target_include_directories(irdet_linux_ncnn_app PRIVATE
    "${CMAKE_CURRENT_LIST_DIR}/include"
    "${IRDET_ZYNQ_PS_INCLUDE}"
    ${IRDET_NCNN_INCLUDE_DIRS}
)

target_compile_definitions(irdet_linux_ncnn_app PRIVATE
    _WIN32_WINNT=0x0601
)

target_link_libraries(irdet_linux_ncnn_app PRIVATE "${IRDET_NCNN_LIBRARY}")

if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
    add_executable(irdet_linux_pl_dw3x3_tool
        "${CMAKE_CURRENT_LIST_DIR}/src/irdet_linux_pl_dw3x3_tool.cpp"
        "${IRDET_ZYNQ_PS_SRC}/ir_pl_dw3x3.c"
        "${IRDET_ZYNQ_PS_SRC}/ir_pl_dw3x3_full.c"
    )

    target_include_directories(irdet_linux_pl_dw3x3_tool PRIVATE
        "${CMAKE_CURRENT_LIST_DIR}/include"
        "${IRDET_ZYNQ_PS_INCLUDE}"
    )
endif()

if(WIN32)
    target_link_libraries(irdet_linux_ncnn_app PRIVATE ws2_32 winmm)
endif()

if(UNIX AND NOT APPLE)
    find_package(Threads REQUIRED)
    target_link_libraries(irdet_linux_ncnn_app PRIVATE Threads::Threads)
endif()
