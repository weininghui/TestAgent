# Examples

Sample SDKs and forge project configs for development, CI, and documentation.

| Directory | Description |
|-----------|-------------|
| [`test_sdk/`](test_sdk/) | Minimal C library (`calc`) |
| [`test_sdk_cpp/`](test_sdk_cpp/) | C++ SDK with namespace, virtual methods, pkg-config |
| [`test_sdk_medium/`](test_sdk_medium/) | Multi-module SDK with `#ifdef` and pkg-config |
| [`forge_test_sdk/`](forge_test_sdk/) | Sample `.forge.json` pointing at `test_sdk` |

Build an SDK fixture from the repo root:

```bash
cmake -S examples/test_sdk -B examples/test_sdk/build
cmake --build examples/test_sdk/build
```
