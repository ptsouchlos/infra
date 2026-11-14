clang_tidy := env('CLANG_TIDY', 'clang-tidy')
tidy_dirs := env('TIDY_DIRS', '.')
_tidy_build_dir := if env('CMAKE_PRESET', '') != '' { 'build/' + env('CMAKE_PRESET', '') } else { env('BUILD_DIR', 'build') }

[unix]
[doc('Run clang-tidy')]
[group('dev')]
lint *args:
    test -f "{{_tidy_build_dir}}/compile_commands.json" || { echo "error: {{_tidy_build_dir}}/compile_commands.json not found; run 'just configure' first" >&2; exit 1; }
    find {{tidy_dirs}} \( -name '.git' -o -name 'infra' -o -name 'vcpkg_installed' -o -name 'node_modules' -o -name 'build*' \) -prune -o -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.cxx' \) -exec {{clang_tidy}} -p "{{_tidy_build_dir}}" {{args}} {} +

[windows]
[doc('Run clang-tidy')]
[group('dev')]
lint *args:
    if (-not (Test-Path '{{_tidy_build_dir}}/compile_commands.json')) { [Console]::Error.WriteLine("error: {{_tidy_build_dir}}/compile_commands.json not found; run 'just configure' first"); exit 1 }
    $roots = '{{tidy_dirs}}' -split '\s+' | Where-Object { $_ }; $files = Get-ChildItem -Path $roots -Recurse -File -Include *.c,*.cc,*.cpp,*.cxx | Where-Object { $_.FullName -notmatch '[\\/](\.git|infra|vcpkg_installed|node_modules|build[^\\/]*)[\\/]' } | ForEach-Object { $_.FullName }; if ($files) { & '{{clang_tidy}}' -p '{{_tidy_build_dir}}' {{args}} @files; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
