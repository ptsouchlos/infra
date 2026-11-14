clang_format := env('CLANG_FORMAT', 'clang-format')
format_dirs := env('FORMAT_DIRS', '.')

[unix]
[doc('Format all C/C++ code')]
[group('dev')]
format *args:
    find {{format_dirs}} \( -name '.git' -o -name 'infra' -o -name 'vcpkg_installed' -o -name 'node_modules' -o -name 'build*' \) -prune -o -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.cxx' -o -name '*.h' -o -name '*.hh' -o -name '*.hpp' -o -name '*.hxx' \) -exec {{clang_format}} -i {{args}} {} +

[windows]
[doc('Format all C/C++ code')]
[group('dev')]
format *args:
    $roots = '{{format_dirs}}' -split '\s+' | Where-Object { $_ }; $files = Get-ChildItem -Path $roots -Recurse -File -Include *.c,*.cc,*.cpp,*.cxx,*.h,*.hh,*.hpp,*.hxx | Where-Object { $_.FullName -notmatch '[\\/](\.git|infra|vcpkg_installed|node_modules|build[^\\/]*)[\\/]' } | ForEach-Object { $_.FullName }; if ($files) { & '{{clang_format}}' -i {{args}} @files; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }

[unix]
[doc('Check C/C++ formatting without modifying files')]
[group('dev')]
format-check *args:
    find {{format_dirs}} \( -name '.git' -o -name 'infra' -o -name 'vcpkg_installed' -o -name 'node_modules' -o -name 'build*' \) -prune -o -type f \( -name '*.c' -o -name '*.cc' -o -name '*.cpp' -o -name '*.cxx' -o -name '*.h' -o -name '*.hh' -o -name '*.hpp' -o -name '*.hxx' \) -exec {{clang_format}} --dry-run --Werror {{args}} {} +

[windows]
[doc('Check C/C++ formatting without modifying files')]
[group('dev')]
format-check *args:
    $roots = '{{format_dirs}}' -split '\s+' | Where-Object { $_ }; $files = Get-ChildItem -Path $roots -Recurse -File -Include *.c,*.cc,*.cpp,*.cxx,*.h,*.hh,*.hpp,*.hxx | Where-Object { $_.FullName -notmatch '[\\/](\.git|infra|vcpkg_installed|node_modules|build[^\\/]*)[\\/]' } | ForEach-Object { $_.FullName }; if ($files) { & '{{clang_format}}' --dry-run --Werror {{args}} @files; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE } }
