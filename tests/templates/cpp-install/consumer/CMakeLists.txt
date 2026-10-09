cmake_minimum_required(VERSION 3.25)
project(consumer LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(foo.bar REQUIRED)

enable_testing()
add_executable(use main.cpp)
target_link_libraries(use PRIVATE foo::bar)
add_test(NAME use COMMAND use)
