cmake_minimum_required(VERSION 3.15)
project(test_package LANGUAGES C)

find_package(fft REQUIRED CONFIG)

add_executable(${PROJECT_NAME} test_package.c)
target_link_libraries(${PROJECT_NAME} PRIVATE fft::fft)
if(MSVC)
    target_compile_definitions(${PROJECT_NAME} PRIVATE "CRT_SECURE_NO_WARNINGS=1")
endif()
