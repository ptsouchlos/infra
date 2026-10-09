# infra

This repo is a set of re-usable components for projects of different languages. It's intended to be included in other projects with [embd](https://www.github.com/ptsouchlos/embd).


## C++ / CMake

`cpp/cmake/` holds independent, includable CMake modules; `cpp/just/cmake.just` holds build recipes.
Vendor the repo with embd, then in your project:

```cmake
list(APPEND CMAKE_MODULE_PATH "${CMAKE_SOURCE_DIR}/<embedded-path>/cpp/cmake")
include(prevent_in_source_builds)   # before project()
project(my_project VERSION 1.0.0 LANGUAGES CXX)
include(project_settings)
include(compiler_warnings)
include(sanitizers)
include(hardening)

# Helpers configure INTERFACE libraries that your targets link against.
add_library(my_project_options INTERFACE)
add_library(my_project_warnings INTERFACE)
pt_set_project_warnings(my_project_warnings ON "" "" "" "")
pt_enable_sanitizers(my_project_options ON OFF ON OFF OFF)  # address leak ubsan thread memory
pt_enable_hardening(my_project_options ON OFF)              # global, ubsan minimal runtime
target_link_libraries(my_exe PRIVATE my_project_options my_project_warnings)
```

Notes: empty warning lists use the defaults; `pt_enable_hardening(... ON ...)` applies globally and so
must run before the targets it should affect are created, as must `pt_enable_ipo()`.

| Module | Provides |
| --- | --- |
| `compiler_warnings` | `pt_set_project_warnings(iface_target warnings_as_errors msvc clang gcc cuda)` |
| `sanitizers` | `pt_enable_sanitizers(iface_target address leak ubsan thread memory)` |
| `hardening` | `pt_enable_hardening(iface_target global ubsan_minimal_runtime)` |
| `static_analyzers` | `pt_enable_clang_tidy`, `pt_enable_cppcheck`, `pt_enable_include_what_you_use` |
| `cache`, `linker`, `ipo` | `pt_enable_cache()`, `pt_configure_linker(target)`, `pt_enable_ipo()` |
| `project_settings` | default build type, `compile_commands.json`, colored diagnostics |
| `prevent_in_source_builds` | fails configure in the source tree |
| `cpm` | bootstraps CPM.cmake (`PT_CPM_VERSION`, `PT_CPM_HASH_SUM`) |
| `install_library` | `pt_install_library(<prefix>.<name> TARGETS ...)` |
| `telemetry` | opt-in build instrumentation (CMake >= 4.3, needs bash and jq) |
| `enable_import_std` | experimental `import std` support |
| `toolchains/*` | gnu, llvm, llvm_libcxx, appleclang, msvc; pass via `CMAKE_TOOLCHAIN_FILE` |

See `NOTICE.md` for upstream attribution.

## Tests

`tests/` generates throwaway projects that exercise each module on Linux, macOS and Windows.
See [tests/README.md](tests/README.md).

## Author

| [<img src="https://avatars0.githubusercontent.com/u/6591180?s=460&v=4" width="100"><br><sub>@ptsouchlos</sub>](https://github.com/ptsouchlos) |
| :-------------------------------------------------------------------------------------------------------------------------------------------: |
