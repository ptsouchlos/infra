# Adapted from cpp-best-practices/cmake_template (Unlicense)
macro(pt_configure_linker project_name)
  set(PT_USER_LINKER_OPTION
    "DEFAULT"
      CACHE STRING "Linker to be used")
    set(PT_USER_LINKER_OPTION_VALUES "DEFAULT" "SYSTEM" "LLD" "GOLD" "BFD" "MOLD" "SOLD" "APPLE_CLASSIC" "MSVC")
  set_property(CACHE PT_USER_LINKER_OPTION PROPERTY STRINGS ${PT_USER_LINKER_OPTION_VALUES})
  list(
    FIND
    PT_USER_LINKER_OPTION_VALUES
    ${PT_USER_LINKER_OPTION}
    PT_USER_LINKER_OPTION_INDEX)

  if(${PT_USER_LINKER_OPTION_INDEX} EQUAL -1)
    message(
      STATUS
        "Using custom linker: '${PT_USER_LINKER_OPTION}', explicitly supported entries are ${PT_USER_LINKER_OPTION_VALUES}")
  endif()

  set_target_properties(${project_name} PROPERTIES LINKER_TYPE "${PT_USER_LINKER_OPTION}")
endmacro()
