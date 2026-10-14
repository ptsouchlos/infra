# Tests

Throwaway projects that prove infra's modules work. Each *kind* is a template under
`templates/<kind>/` with a `manifest.json`; directories starting with `_` are shared fragments.

## Run

```sh
python3 -m unittest discover -s tests          # unit tests for the generator and runner
uv run tests/run.py --all                      # generate and run every kind
uv run tests/run.py cpp-install                # one kind
uv run tests/run.py cpp-toolchain --set TOOLCHAIN=llvm
uv run tests/run.py cpp-basic --cmake-arg=-DCMAKE_CXX_COMPILER=clang++ --cmake-arg=-GNinja
uv run tests/generate.py --list                # kinds and descriptions
uv run tests/generate.py cpp-basic ./scratch   # generate only, to poke at it by hand
```

Exit codes of `run.py`: 0 pass or skipped, 1 a step failed, 2 usage error, 3 a required tool is missing.
`run.py` deletes its temporary project after a pass; use `--keep` or `--work-dir` to inspect it.
Use the `--cmake-arg=...` form (with `=`) because the value starts with a dash.

## Kinds

| Kind | Proves |
| --- | --- |
| `cpp-basic` | project settings, compiler warnings as errors, in-source-build guard module |
| `cpp-sanitizers` | `pt_enable_sanitizers` flags reach the compile line (not run on Windows) |
| `cpp-hardening` | `pt_enable_hardening` configures and builds |
| `cpp-install` | `pt_install_library` output is found by a separate consumer via `find_package` |
| `cpp-cpm` | `cpm` bootstrap fetches and builds a pinned dependency (network) |
| `cpp-toolchain` | a toolchain file configures and builds (`--set TOOLCHAIN=...`) |
| `cpp-just` | `cpp/just/cmake.just` configure, build and test recipes (also run natively on all three OSes in CI) |
| `cpp-cache` | `pt_enable_cache` makes ccache the compiler launcher (needs `ccache`; not run on Windows, where the Visual Studio generators ignore compiler launchers) |
| `cpp-linker` | `pt_configure_linker` configures and builds; `--set LINKER=LLD --set LINK_FLAG=-fuse-ld=lld` also checks the flag reaches the link line (`MOLD`: `-fuse-ld=mold`) |
| `cpp-ipo` | `pt_enable_ipo` adds `-flto` to the build (`--set IPO_FLAG=/GL` for MSVC; the Visual Studio generators do not echo compiler flags, so CI on Windows passes `--set IPO_FLAG=` and only checks build and test) |
| `cpp-static-analyzers` | cppcheck, clang-tidy and include-what-you-use run during the build (needs all three; not run on macOS or Windows; the kind ships a `.clang-tidy` because clang-tidy refuses to run with no checks) |
| `cpp-static-analyzers-error` | negative case: a cppcheck `uninitvar` finding fails the build when warnings are errors |
| `cpp-telemetry` | including `telemetry` enables build instrumentation and traces land in `<build>/.trace` (needs CMake 4.3 or newer, `bash` and `jq`; older CMake makes the configure assertion fail) |
| `cpp-import-std` | `enable_import_std` lets `import std;` build (needs CMake 4.3 or newer, Ninja and a toolchain with a std module: gcc 15+, clang 18+ with libc++, or MSVC; not run on macOS). On the dev host both gcc 16 and clang 22 with `--cmake-arg=-DCMAKE_CXX_FLAGS=-stdlib=libc++` pass |
| `cpp-in-source`, `cpp-warnings-error` | negative cases: the expected failure happens |
| `rust-basic` | `rust/just/{format,clippy}.just` recipes |

The two `just` kinds need `just` 1.27.0 or newer (older versions reject the `[doc]` attribute); CI
checks the floor with a `just-min` job.
| `docs` | Doxygen builds from a plain `Doxyfile` |

## Add a kind

1. Create `templates/<kind>/manifest.json` with `description`, `steps`, and optionally
   `includes` (templates copied first; later ones override), `vars` (defaults for `--set`),
   and `skip_on` (`linux`, `darwin`, `windows`).
2. A step is a preset name (`cmake-configure`, `cmake-build`, `cmake-test`) or an object with
   `name`, `cmd` (argv list, no shell), and optional `cwd`, `expect` (`pass`/`fail`),
   `expect_output` (substring of combined output), `extra_args` (receives `--cmake-arg` values).
   An object may also carry `preset` to override one field of a preset.
3. Use `@INFRA_DIR@`, `@PROJECT_DIR@`, `@BUILD_DIR@`, `@PREFIX@`, `@PYTHON@`, `@PROJECT_NAME@` and
   your `vars` as `@TOKENS@` in files and steps. An unresolved token is an error.
4. Add a test to `test_generate.py` and run the unit tests.

Manifest extras: `requires` lists tools a kind needs beyond its step commands, keyed by `all`,
`linux`, `darwin` or `windows` (for example `{"all": ["git"]}`); a missing tool exits 3 before any
step runs. Runner options: `--timeout SECONDS` (default 1800) kills a hung step, and `--verbose`
streams output as it is produced. `--set` values must be `KEY=VALUE`. The infra checkout path must
not contain a single quote (just `import` strings cannot hold one).

## Action tests

`test_actions.py` checks the composite actions in `.github/actions/`: structure rules (shell on every
run step, no PowerShell-only code, pinned third-party actions) and the `install.sh`/`run.sh`
scripts. The build tests need cmake, ninja and a C++ compiler and are skipped without them.
