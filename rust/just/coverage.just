cov_format := env('COV_FORMAT', '')
_cov_flag := if cov_format == 'lcov' { '--lcov --output-path lcov.info' } else if cov_format != '' { '--' + cov_format } else { '' }

[doc('Run Rust tests with coverage via cargo-llvm-cov (COV_FORMAT=lcov|html|summary-only)')]
[group('test')]
coverage *args:
    cargo llvm-cov {{_cov_flag}} {{args}}

[doc('Clean cargo-llvm-cov artifacts')]
[group('test')]
coverage-clean:
    cargo llvm-cov clean --workspace
