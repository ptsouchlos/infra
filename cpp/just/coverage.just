cov_tool := env('COV_TOOL', 'auto')
gcovr := env('GCOVR', 'gcovr')
llvm_cov := env('LLVM_COV', 'llvm-cov')
llvm_profdata := env('LLVM_PROFDATA', 'llvm-profdata')
_cov_build_dir := if env('CMAKE_PRESET', '') != '' { 'build/' + env('CMAKE_PRESET', '') } else { env('BUILD_DIR', 'build') }

[unix]
[doc('Generate C/C++ coverage report (gcovr for GCC, llvm-cov for Clang; COV_TOOL=auto|gcovr|llvm-cov)')]
[group('test')]
coverage *args:
    #!/usr/bin/env bash
    set -euo pipefail
    bd="{{_cov_build_dir}}"
    tool="{{cov_tool}}"
    if [ ! -d "$bd" ]; then
        echo "error: build directory '$bd' not found; run 'just configure', 'just build', and 'just test' first" >&2
        exit 1
    fi
    if [ "$tool" = "auto" ]; then
        if find "$bd" -name '*.profraw' -print -quit | grep -q .; then
            tool="llvm-cov"
        elif find "$bd" \( -name '*.gcda' -o -name '*.gcno' \) -print -quit | grep -q .; then
            tool="gcovr"
        else
            echo "error: no .profraw or .gcda/.gcno files found in '$bd'; build with pt_enable_coverage and run 'just test' first" >&2
            exit 1
        fi
    fi
    case "$tool" in
        gcovr)
            "{{gcovr}}" -r . "$bd" {{args}}
            ;;
        llvm-cov)
            profraws=()
            while IFS= read -r p; do
                profraws+=("$p")
            done < <(find "$bd" -name '*.profraw' | sort)
            if [ "${#profraws[@]}" -eq 0 ]; then
                echo "error: no .profraw files found in '$bd'" >&2
                exit 1
            fi
            "{{llvm_profdata}}" merge -sparse "${profraws[@]}" -o "$bd/default.profdata"
            bins=()
            while IFS= read -r bin; do
                bins+=(-object "$bin")
            done < <(find "$bd" -maxdepth 3 -type f -perm -111 ! -name '*.so*' ! -name '*.dylib' ! -path '*/CMakeFiles/*' | sort)
            if [ "${#bins[@]}" -eq 0 ]; then
                echo "error: no instrumented binaries found in '$bd'" >&2
                exit 1
            fi
            "{{llvm_cov}}" report "${bins[@]}" -instr-profile="$bd/default.profdata" {{args}}
            ;;
        *)
            echo "error: unsupported COV_TOOL '$tool' (expected auto, gcovr, or llvm-cov)" >&2
            exit 1
            ;;
    esac

[windows]
[doc('Generate C/C++ coverage report (gcovr for GCC, llvm-cov for Clang; COV_TOOL=auto|gcovr|llvm-cov)')]
[group('test')]
coverage *args:
    $bd = '{{_cov_build_dir}}'; $tool = '{{cov_tool}}'; if (-not (Test-Path $bd)) { [Console]::Error.WriteLine("error: build directory '$bd' not found; run 'just configure', 'just build', and 'just test' first"); exit 1 }; if ($tool -eq 'auto') { if (Get-ChildItem -Path $bd -Recurse -Filter *.profraw | Select-Object -First 1) { $tool = 'llvm-cov' } elseif (Get-ChildItem -Path $bd -Recurse -Include *.gcda,*.gcno | Select-Object -First 1) { $tool = 'gcovr' } else { [Console]::Error.WriteLine("error: no .profraw or .gcda/.gcno files found in '$bd'"); exit 1 } }; if ($tool -eq 'gcovr') { & '{{gcovr}}' -r . $bd {{args}}; exit $LASTEXITCODE } elseif ($tool -eq 'llvm-cov') { $profraws = Get-ChildItem -Path $bd -Recurse -Filter *.profraw | ForEach-Object { $_.FullName }; & '{{llvm_profdata}}' merge -sparse @profraws -o "$bd/default.profdata"; if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }; $bins = Get-ChildItem -Path $bd -Recurse -Filter *.exe | Where-Object { $_.FullName -notmatch '[\\/]CMakeFiles[\\/]' } | ForEach-Object { '-object'; $_.FullName }; & '{{llvm_cov}}' report @bins "-instr-profile=$bd/default.profdata" {{args}}; exit $LASTEXITCODE } else { [Console]::Error.WriteLine("error: unsupported COV_TOOL '$tool'"); exit 1 }
