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
| `cpp-in-source`, `cpp-warnings-error` | negative cases: the expected failure happens |
| `rust-basic` | `rust/just/{format,clippy}.just` recipes |
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
