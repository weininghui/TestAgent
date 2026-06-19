cmake_minimum_required(VERSION 3.14)
project(my_sdk CXX)

add_library(my_sdk STATIC src/api.cpp)
target_include_directories(my_sdk PUBLIC
    $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
    $<INSTALL_INTERFACE:include>
)
set_target_properties(my_sdk PROPERTIES
    OUTPUT_NAME my_sdk
    VERSION 1.0.0
)

include(GNUInstallDirs)
install(TARGETS my_sdk
    EXPORT my_sdkTargets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
    LIBRARY DESTINATION ${CMAKE_INSTALL_LIBDIR}
    RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR}
)
install(DIRECTORY include/ DESTINATION ${CMAKE_INSTALL_INCLUDEDIR})
install(EXPORT my_sdkTargets
    FILE my_sdkTargets.cmake
    NAMESPACE my_sdk::
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/my_sdk
)

include(CMakePackageConfigHelpers)
configure_package_config_file(
    ${CMAKE_CURRENT_SOURCE_DIR}/my_sdkConfig.cmake.in
    ${CMAKE_CURRENT_BINARY_DIR}/my_sdkConfig.cmake
    INSTALL_DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/my_sdk
)
write_basic_package_version_file(
    ${CMAKE_CURRENT_BINARY_DIR}/my_sdkConfigVersion.cmake
    VERSION 1.0.0
    COMPATIBILITY SameMajorVersion
)
install(FILES
    ${CMAKE_CURRENT_BINARY_DIR}/my_sdkConfig.cmake
    ${CMAKE_CURRENT_BINARY_DIR}/my_sdkConfigVersion.cmake
    DESTINATION ${CMAKE_INSTALL_LIBDIR}/cmake/my_sdk
)

configure_file(my_sdk.pc.in ${CMAKE_CURRENT_BINARY_DIR}/my_sdk.pc @ONLY)
install(FILES ${CMAKE_CURRENT_BINARY_DIR}/my_sdk.pc DESTINATION ${CMAKE_INSTALL_LIBDIR}/pkgconfig)
