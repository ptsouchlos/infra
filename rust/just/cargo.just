profile := env('CARGO_PROFILE', 'dev')
target := env('CARGO_TARGET', '')
target_flag := if target != '' { '--target ' + target } else { '' }

[doc('Build the crate (CARGO_PROFILE selects the profile, default dev; CARGO_TARGET a target triple)')]
[group('build')]
build *args:
    cargo build --profile {{profile}} {{target_flag}} {{args}}

[doc('Build the crate with the release profile (CARGO_TARGET selects a target triple)')]
[group('build')]
build-release *args:
    cargo build --release {{target_flag}} {{args}}

[doc('Run the default binary (pass cargo args before --, program args after)')]
[group('build')]
run *args:
    cargo run --profile {{profile}} {{target_flag}} {{args}}

[doc('Run the default binary with the release profile')]
[group('build')]
run-release *args:
    cargo run --release {{target_flag}} {{args}}

[doc('Run the tests (CARGO_TARGET selects a target triple)')]
[group('test')]
test *args:
    cargo test {{target_flag}} {{args}}

[doc('Type-check without producing binaries (CARGO_TARGET selects a target triple)')]
[group('build')]
check *args:
    cargo check --all-targets {{target_flag}} {{args}}

[doc('Remove the target directory')]
[group('build')]
clean:
    cargo clean
