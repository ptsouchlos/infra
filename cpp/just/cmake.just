build_dir := env('BUILD_DIR', 'build')
preset := env('CMAKE_PRESET', '')
config := env('BUILD_CONFIG', 'Debug')

[doc('Configure the CMake project (set CMAKE_PRESET to use a preset)')]
[group('build')]
configure *args:
    cmake {{ if preset != '' { '--preset ' + preset } else { '-S . -B ' + build_dir + ' -DCMAKE_BUILD_TYPE=' + config } }} {{args}}

[doc('Build the CMake project (BUILD_CONFIG selects the configuration, default Debug)')]
[group('build')]
build *args:
    cmake --build {{ build_dir }} --config {{ config }} {{args}}

[doc('Run the tests with CTest (BUILD_CONFIG selects the configuration, default Debug)')]
[group('test')]
test *args:
    ctest --test-dir {{ build_dir }} --build-config {{ config }} --output-on-failure {{args}}

[doc('Remove the build directory')]
[group('build')]
clean:
    cmake -E rm -rf {{ build_dir }}
