clang_tidy := env('CLANG_TIDY', 'clang-tidy')
tidy_dirs := env('TIDY_DIRS', '')
_tidy_py := if os_family() == 'windows' { 'python' } else { 'python3' }
_tidy_build_dir := if env('CMAKE_PRESET', '') != '' { 'build/' + env('CMAKE_PRESET', '') } else { env('BUILD_DIR', 'build') }

[doc('Run clang-tidy')]
[group('dev')]
lint *args:
    {{_tidy_py}} -c "import pathlib, shlex, subprocess, sys; bd = pathlib.Path(sys.argv[1]); cc = bd / 'compile_commands.json'; cc.is_file() or sys.exit(f'error: {cc} not found; run just configure first'); exts = {'.c', '.cc', '.cpp', '.cxx'}; skip = {'.git', 'infra', 'vcpkg_installed', 'node_modules'}; roots = [p for p in sys.argv[2].split() if p] or ['.']; files = sorted(str(p) for r in roots for p in (pathlib.Path(r).rglob('*') if pathlib.Path(r).is_dir() else [pathlib.Path(r)]) if p.is_file() and p.suffix.lower() in exts and not any(part in skip or part.startswith('build') for part in p.parts)); sys.exit(0 if not files else subprocess.call([sys.argv[3], '-p', str(bd), *shlex.split(sys.argv[4]), *files]))" "{{_tidy_build_dir}}" "{{tidy_dirs}}" "{{clang_tidy}}" "{{args}}"
