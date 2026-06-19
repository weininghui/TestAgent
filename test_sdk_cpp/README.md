# test_sdk_cpp

Sample C++ SDK fixture for TestAgent v2.5 integration tests.

Features exercised:

- Namespaces (`my_sdk`)
- Classes with virtual/static methods
- Template functions (`clamp`)
- `enum class`
- pkg-config (`.pc`) and CMake package config

## Build

```bash
cmake -S . -B build
cmake --build build
```

## Install (for pkg-config / find_package tests)

```bash
cmake --install build --prefix /tmp/my_sdk_install
export PKG_CONFIG_PATH=/tmp/my_sdk_install/lib/pkgconfig:$PKG_CONFIG_PATH
pkg-config --cflags --libs my_sdk
```
