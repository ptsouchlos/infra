profile := env('CARGO_PROFILE', 'dev')

[doc('Build the crate (CARGO_PROFILE selects the profile, default dev)')]
[group('build')]
build *args:
    cargo build --profile {{profile}} {{args}}

[doc('Build the crate with the release profile')]
[group('build')]
build-release *args:
    cargo build --release {{args}}

[doc('Run the default binary (pass cargo args before --, program args after)')]
[group('build')]
run *args:
    cargo run --profile {{profile}} {{args}}

[doc('Run the default binary with the release profile')]
[group('build')]
run-release *args:
    cargo run --release {{args}}

[doc('Run the tests')]
[group('test')]
test *args:
    cargo test {{args}}

[doc('Type-check without producing binaries')]
[group('build')]
check *args:
    cargo check --all-targets {{args}}

[doc('Remove the target directory')]
[group('build')]
clean:
    cargo clean
