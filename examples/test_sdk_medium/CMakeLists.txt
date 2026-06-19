cmake_minimum_required(VERSION 3.14)
project(medium CXX)

add_library(medium STATIC src/core.cpp src/net.cpp)
target_include_directories(medium PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
target_compile_definitions(medium PUBLIC MEDIUM_NET=1)

include(GNUInstallDirs)
install(TARGETS medium EXPORT mediumTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR})
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT mediumTargets
    FILE mediumTargets.cmake
    NAMESPACE medium::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/medium)

configure_file(medium.pc.in ${CMAKE_CURRENT_BINARY_DIR}/medium.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/medium.pc DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
