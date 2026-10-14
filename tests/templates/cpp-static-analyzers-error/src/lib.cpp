#include "lib.hpp"

int twice(int value) {
    int unset;
    return value * 2 + unset;  // cppcheck: uninitvar
}
