build_dir := env('BUILD_DIR', 'build')
preset := env('CMAKE_PRESET', '')

[doc('Configure the CMake project (set CMAKE_PRESET to use a preset)')]
[group('build')]
configure *args:
    cmake {{ if preset != '' { '--preset ' + preset } else { '-S . -B ' + build_dir } }} {{args}}

[doc('Build the CMake project')]
[group('build')]
build *args:
    cmake --build {{ build_dir }} {{args}}

[doc('Run the tests with CTest')]
[group('test')]
test *args:
    ctest --test-dir {{ build_dir }} --output-on-failure {{args}}

[doc('Remove the build directory')]
[group('build')]
clean:
    cmake -E rm -rf {{ build_dir }}
