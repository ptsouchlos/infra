# Notice

The C++/CMake modules under `cpp/cmake/` are adapted from:

- [bemanproject/infra](https://github.com/bemanproject/infra) — Apache-2.0 WITH LLVM-exception.
  Source of `install_library.cmake`, `Config.cmake.in`, `telemetry.cmake`, `telemetry.sh`,
  `enable_import_std.cmake` and `toolchains/`. Upstream SPDX headers are retained.
- [cpp-best-practices/cmake_template](https://github.com/cpp-best-practices/cmake_template) — Unlicense.
  Source of `compiler_warnings.cmake`, `sanitizers.cmake`, `hardening.cmake`,
  `static_analyzers.cmake`, `cache.cmake`, `linker.cmake`, `ipo.cmake`,
  `project_settings.cmake` and `prevent_in_source_builds.cmake`.
- [cpm-cmake/CPM.cmake](https://github.com/cpm-cmake/CPM.cmake) — MIT, Copyright (c) 2019-2023
  Lars Melchior and contributors. `cpm.cmake` bootstraps a pinned release.

Functions, options and cache variables were renamed to a `pt_` / `PT_` prefix.
