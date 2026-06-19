cmake_minimum_required(VERSION 3.14)
project(test_sdk C)

add_library(calc STATIC src/calc.c)
target_include_directories(calc PUBLIC ${CMAKE_CURRENT_SOURCE_DIR}/include)
