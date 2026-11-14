clang_format := env('CLANG_FORMAT', 'clang-format')
format_dirs := env('FORMAT_DIRS', '')
_format_py := if os_family() == 'windows' { 'python' } else { 'python3' }

[doc('Format all C/C++ code')]
[group('dev')]
format *args:
    {{_format_py}} -c "import pathlib, shlex, subprocess, sys; exts = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx'}; skip = {'.git', 'infra', 'vcpkg_installed', 'node_modules'}; roots = [p for p in sys.argv[2].split() if p] or ['.']; files = sorted(str(p) for r in roots for p in (pathlib.Path(r).rglob('*') if pathlib.Path(r).is_dir() else [pathlib.Path(r)]) if p.is_file() and p.suffix.lower() in exts and not any(part in skip or part.startswith('build') for part in p.parts)); sys.exit(0 if not files else subprocess.call([sys.argv[1], '-i', *shlex.split(sys.argv[3]), *files]))" "{{clang_format}}" "{{format_dirs}}" "{{args}}"

[doc('Check C/C++ formatting without modifying files')]
[group('dev')]
format-check *args:
    {{_format_py}} -c "import pathlib, shlex, subprocess, sys; exts = {'.c', '.cc', '.cpp', '.cxx', '.h', '.hh', '.hpp', '.hxx'}; skip = {'.git', 'infra', 'vcpkg_installed', 'node_modules'}; roots = [p for p in sys.argv[2].split() if p] or ['.']; files = sorted(str(p) for r in roots for p in (pathlib.Path(r).rglob('*') if pathlib.Path(r).is_dir() else [pathlib.Path(r)]) if p.is_file() and p.suffix.lower() in exts and not any(part in skip or part.startswith('build') for part in p.parts)); sys.exit(0 if not files else subprocess.call([sys.argv[1], '--dry-run', '--Werror', *shlex.split(sys.argv[3]), *files]))" "{{clang_format}}" "{{format_dirs}}" "{{args}}"
