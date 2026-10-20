# infra

This repo is a set of re-usable components for projects of different languages. It's intended to be included in other projects with [embd](https://www.github.com/ptsouchlos/embd).


## C++ / CMake

`cpp/cmake/` holds independent, includable CMake modules; `cpp/just/cmake.just` holds build recipes (the `just` recipes in this repo need `just` 1.27.0 or newer, for the `[doc]` attribute).
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

## Shared CI actions

`.github/actions/` holds composite GitHub Actions for downstream repos. Reference them by tag:
`ptsouchlos/infra/.github/actions/<name>@v1`.

| Action | Inputs | Does |
| --- | --- | --- |
| `setup-cpp` | `compiler`, `version`, `cmake-version` | installs the compiler (and CMake/Ninja when missing or pinned), exports `CC`/`CXX`, sets up MSVC on Windows |
| `cmake-build` | `source-dir`, `build-dir`, `build-type`, `preset`, `configure-args`, `test`, `install-prefix`, `ccache`, `cpm-cache` | configure, build, ctest, optional install |
| `setup-rust` | `toolchain`, `components`, `targets`, `just` | rustup toolchain and targets (a Linux `-musl` target also installs `musl-tools`), cargo cache, optional `just` |
| `cargo-release` | `target`, `bin`, `name`, `archive`, `working-directory`, `cargo-args`, `out-dir`, `release` | `cargo build --release` for one target, package (tar.gz, zip or the bare binary), write a `.sha256`, optionally upload to the tag's release |
| `cargo-check` | `working-directory`, `fmt`, `clippy`, `clippy-args`, `test`, `args` | `cargo fmt --check`, clippy, test (`args` goes to clippy and test, not fmt) |
| `build-docs` | `working-directory`, `doxyfile`, `html-dir`, `publish` | Doxygen + Graphviz, build, optional Pages deploy |
| `update-infra` | `tag`, `token`, `branch` | moves the repo's infra embeds (and `@vN` action refs on a major) to a release, then opens or updates a PR |

```yaml
jobs:
  build:
    strategy:
      matrix:
        include:
          - { os: ubuntu-latest, compiler: gcc, version: 14 }
          - { os: ubuntu-latest, compiler: clang, version: 18 }
          - { os: macos-latest, compiler: appleclang }
          - { os: windows-latest, compiler: msvc }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: ptsouchlos/infra/.github/actions/setup-cpp@v1
        with: { compiler: "${{ matrix.compiler }}", version: "${{ matrix.version }}" }
      - uses: ptsouchlos/infra/.github/actions/cmake-build@v1
        with: { ccache: "true", cpm-cache: "true" }
```

```yaml
jobs:
  rust:
    strategy:
      matrix:
        os: [ubuntu-latest, macos-latest, windows-latest]
        toolchain: [stable]
        include:
          - { os: ubuntu-latest, toolchain: beta }
          - { os: ubuntu-latest, toolchain: "1.85" }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: ptsouchlos/infra/.github/actions/setup-rust@v1
        with: { toolchain: "${{ matrix.toolchain }}" }
      - uses: ptsouchlos/infra/.github/actions/cargo-check@v1
```

```yaml
jobs:
  release:
    permissions:
      contents: write
    strategy:
      fail-fast: false
      matrix:
        include:
          - { os: ubuntu-latest, target: x86_64-unknown-linux-musl }
          - { os: ubuntu-24.04-arm, target: aarch64-unknown-linux-musl }
          - { os: macos-latest, target: aarch64-apple-darwin }
          - { os: windows-latest, target: x86_64-pc-windows-msvc }
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/checkout@v4
      - uses: ptsouchlos/infra/.github/actions/setup-rust@v1
        with: { components: "", targets: "${{ matrix.target }}" }
      - uses: ptsouchlos/infra/.github/actions/cargo-release@v1
        with:
          target: ${{ matrix.target }}
          bin: my-tool
          release: ${{ startsWith(github.ref, 'refs/tags/') }}
```

Notes:
- `toolchain` takes a channel (`stable`, `beta`, `nightly`) or a version (`1.85`). The cargo cache is keyed per rustc version, so toolchain legs never share a cache. Nightly sometimes ships without `rustfmt` or `clippy`, so mark a nightly leg `continue-on-error: true`.
- `cargo-release` builds for the runner's own architecture only; cross-linking (for example x86_64 to aarch64) is not supported, so run each target on a matching runner.
- `cargo-release` assets: the archive holds just the binary at its root, and `<asset>.sha256` holds `<hash>  <bare file name>`, so `sha256sum -c` works from the download directory.
- Supported compiler/OS pairs: Linux gcc and clang, macOS appleclang, Windows msvc and clang. Anything else fails fast.
- `configure-args`, `clippy-args`, `args` and `cargo-args` are split on spaces, so one argument cannot contain a space: write `--features=a,b`, not `--features "a b"`.
- With a `preset`, the preset runs the configure step and `build-dir` must equal its `binaryDir`.
- Use forward slashes in paths on Windows (`install-prefix`, `build-dir`).
- `build-docs` with `publish: true` needs `permissions: { pages: write, id-token: write }` and the `github-pages` environment.

### Keeping a consumer up to date

Call the reusable workflow from `.github/workflows/infra-update.yml`. The caller owns the triggers;
the token, checkout and PR steps live in infra, so fixes reach every consumer with the next `v1`:

```yaml
name: Update infra
on:
  repository_dispatch: { types: [infra-release] }
  schedule: [{ cron: "0 6 * * 1" }]
  workflow_dispatch:
concurrency: infra-update
jobs:
  update:
    uses: ptsouchlos/infra/.github/workflows/update-infra.yml@v1
    secrets: inherit
    with:
      tag: ${{ github.event.client_payload.tag }}
```

It mints a GitHub App token (not `GITHUB_TOKEN`, whose PRs do not trigger CI). To use the
`update-infra` action directly instead, pass it a token from `actions/create-github-app-token`.

Per consumer repo, install the App on it and run:

```sh
gh repo edit R --add-topic uses-infra
gh variable set INFRA_BOT_APP_ID -R R
gh secret set INFRA_BOT_PRIVATE_KEY -R R < key.pem
```

A drifted vendored file makes the step fail instead of being overwritten; fix it by hand.

### Releasing

Push a `vX.Y.Z` tag. `release.yml` moves the floating `vX` tag to it and creates a GitHub release
with generated notes. Downstream repos pin `@vX` and get the update. The first release should be
`v1.0.0`; until it exists, `@v1` does not resolve.

## Author

| [<img src="https://avatars0.githubusercontent.com/u/6591180?s=460&v=4" width="100"><br><sub>@ptsouchlos</sub>](https://github.com/ptsouchlos) |
| :-------------------------------------------------------------------------------------------------------------------------------------------: |
