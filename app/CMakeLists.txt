# ./app/CMakeLists.txt

cmake_minimum_required(VERSION 3.24)
cmake_policy(VERSION 3.24)
cmake_policy(SET CMP0077 NEW)


function(handle_runtime_dependencies TARGET_NAME)
  install(CODE [[
    file(GET_RUNTIME_DEPENDENCIES
      EXECUTABLES
      "$<TARGET_FILE:${TARGET_NAME}>"

      RESOLVED_DEPENDENCIES_VAR   _r_deps
      UNRESOLVED_DEPENDENCIES_VAR _u_deps

      PRE_INCLUDE_REGEXES
      ".*msvcp.*\\.dll$"
      ".*vcruntime.*\\.dll$"
      ".*ucrtbase\\.dll$"
      ".*python.*\\.dll$"
      ".*zlib1\\.dll$"

      PRE_EXCLUDE_REGEXES
      ".*"
    )

    foreach(d IN LISTS _r_deps)
      file(INSTALL
      DESTINATION "${CMAKE_INSTALL_PREFIX}"
      TYPE        SHARED_LIBRARY
      FILES       "${d}"
      FOLLOW_SYMLINK_CHAIN
      )
    endforeach()

    if(_u_deps)
      message(WARNING "Some requested DLLs weren't found: ${_u_deps}")
    endif()
  ]])
endfunction()


# ───────────────────────────────────────────────────────────
# global settings
# ───────────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)   # useful for static libs / shared code

# default to Release unless user says otherwise
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif()

set(App_VERSION "0.0.0" CACHE STRING "App version")

include(cmake/vcpkg-bootstrap.cmake)  # bootstrap vcpkg for python

project(ExpenseTracker VERSION ${App_VERSION} LANGUAGES CXX)

message(STATUS "[App] Version ........: ${App_VERSION}")
message(STATUS "[App] Build type .....: ${CMAKE_BUILD_TYPE}")
message(STATUS "[App] Generator ......: ${CMAKE_GENERATOR}")


# ───────────────────────────────────────────────────────────
# build options
# ───────────────────────────────────────────────────────────
option(BUILD_PYTHON_INTERPRETER "Build embedded Python interpreter" ON)
option(BUILD_PYTHON_LAUNCHER    "Build python module launcher"      ON)
option(INSTALL_REQUIREMENTS     "Install requirements.txt"          ON)
option(INSTALL_MODULE           "Install main python module"        ON)
option(INSTALL_STDLIB           "Install standard Python libraries" ON)
option(BUILD_TESTS              "Build unit tests"                  ON)

foreach(opt
        BUILD_PYTHON_INTERPRETER
        BUILD_PYTHON_LAUNCHER
        INSTALL_REQUIREMENTS
        INSTALL_MODULE
        INSTALL_STDLIB
        BUILD_TESTS)
    set(${opt} "${${opt}}" CACHE BOOL " ")
endforeach()

message(STATUS "[Options]")
foreach(opt
        BUILD_PYTHON_INTERPRETER
        BUILD_PYTHON_LAUNCHER
        INSTALL_REQUIREMENTS
        INSTALL_MODULE
        INSTALL_STDLIB
        BUILD_TESTS)
    message(STATUS "  - ${opt}: ${${opt}}")
endforeach()


# common helper sources (compiled into each exe)
set(DIST_SOURCES src/dist.cpp)
set(DIST_INCLUDES include)   # contains dist.h



# ───────────────────────────────────────────────────────────
# resources (only meaningful on Windows)
# ───────────────────────────────────────────────────────────
if(WIN32)
    configure_file(
        "${CMAKE_SOURCE_DIR}/rsc/icon.ico"
        "${CMAKE_BINARY_DIR}/rsc/icon.ico"
        COPYONLY
    )
    file(COPY "${CMAKE_SOURCE_DIR}/rsc/app.rc"
         DESTINATION "${CMAKE_BINARY_DIR}/rsc")
    set(APP_RC $<$<BOOL:WIN32>:${CMAKE_BINARY_DIR}/rsc/app.rc>)
endif()



# ───────────────────────────────────────────────────────────
# embedded Python interpreter
# ───────────────────────────────────────────────────────────
if(BUILD_PYTHON_INTERPRETER)
    message(STATUS "[App] [*] Python interpreter")

    find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

    add_executable(PyInterpreter
        src/PythonInterpreter.cpp
        ${DIST_SOURCES}
        ${APP_RC}
    )
    target_include_directories(PyInterpreter
        PRIVATE
        ${DIST_INCLUDES}
        Python3::Python
    )
    target_link_libraries(PyInterpreter
        PRIVATE
        Python3::Python
    )
    target_compile_definitions(PyInterpreter PUBLIC UNICODE _UNICODE App_VERSION="${App_VERSION}")
    if(MSVC)
        target_compile_options(PyInterpreter PRIVATE /utf-8)
    endif()
    set_target_properties(PyInterpreter PROPERTIES OUTPUT_NAME "python")
    
    install(TARGETS PyInterpreter RUNTIME DESTINATION .)
    install(CODE [[
        file(GET_RUNTIME_DEPENDENCIES
            EXECUTABLES
            "$<TARGET_FILE:PyInterpreter>"

            RESOLVED_DEPENDENCIES_VAR   _r_deps
            UNRESOLVED_DEPENDENCIES_VAR _u_deps

            PRE_INCLUDE_REGEXES
            ".*msvcp.*\\.dll$"
            ".*vcruntime.*\\.dll$"
            ".*ucrtbase\\.dll$"
            ".*python.*\\.dll$"
            ".*zlib1\\.dll$"

            PRE_EXCLUDE_REGEXES
            ".*"
        )

        foreach(d IN LISTS _r_deps)
            file(INSTALL
            DESTINATION "${CMAKE_INSTALL_PREFIX}"
            TYPE        SHARED_LIBRARY
            FILES       "${d}"
            FOLLOW_SYMLINK_CHAIN
            )
        endforeach()

        if(_u_deps)
            message(WARNING "Some requested DLLs weren’t found: ${_u_deps}")
        endif()
        ]])


else()
    message(STATUS "[App] [ ] Python interpreter (disabled)")
endif()



# ───────────────────────────────────────────────────────────
# ExpenseTracker launcher stub
# ───────────────────────────────────────────────────────────
if(BUILD_PYTHON_LAUNCHER)
    message(STATUS "[App] [*] Python launcher")

    find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

    add_executable(PyLauncher
        src/PythonLauncher.cpp
        ${DIST_SOURCES}
        ${APP_RC}
    )
    target_include_directories(PyLauncher
        PRIVATE
        ${DIST_INCLUDES}
        Python3::Python
    )
    target_link_libraries(PyLauncher
        PRIVATE
        Python3::Python
    )
    target_compile_definitions(PyLauncher PUBLIC UNICODE _UNICODE App_VERSION="${App_VERSION}")
    if(MSVC)
        target_compile_options(PyLauncher PRIVATE /utf-8)
    endif()
    set_target_properties(PyLauncher PROPERTIES OUTPUT_NAME "ExpenseTracker")
    install(TARGETS PyLauncher RUNTIME DESTINATION .)
    install(CODE [[
        file(GET_RUNTIME_DEPENDENCIES
            EXECUTABLES
            "$<TARGET_FILE:PyLauncher>"

            RESOLVED_DEPENDENCIES_VAR   _r_deps
            UNRESOLVED_DEPENDENCIES_VAR _u_deps

            PRE_INCLUDE_REGEXES
            ".*msvcp.*\\.dll$"
            ".*vcruntime.*\\.dll$"
            ".*ucrtbase\\.dll$"
            ".*python.*\\.dll$"
            ".*zlib1\\.dll$"

            PRE_EXCLUDE_REGEXES
            ".*"
        )

        foreach(d IN LISTS _r_deps)
            file(INSTALL
            DESTINATION "${CMAKE_INSTALL_PREFIX}"
            TYPE        SHARED_LIBRARY
            FILES       "${d}"
            FOLLOW_SYMLINK_CHAIN
            )
        endforeach()

        if(_u_deps)
            message(WARNING "Some requested DLLs weren’t found: ${_u_deps}")
        endif()
        ]])
else()
    message(STATUS "[App] [ ] Python launcher (disabled)")
endif()



# ───────────────────────────────────────────────────────────
# Python dependency bundle
# ───────────────────────────────────────────────────────────
if (INSTALL_REQUIREMENTS)      
  message(STATUS "[App] [*] Install requirements.txt")
  find_package(Python3 REQUIRED COMPONENTS Interpreter)

  install(CODE [[
    # Locate requirements.txt
    set(REQUIREMENTS_FILE "${CMAKE_SOURCE_DIR}/../requirements.txt")
    if (NOT EXISTS "${REQUIREMENTS_FILE}")
      message(FATAL_ERROR "requirements.txt not found: ${REQUIREMENTS_FILE}")
    endif()

    # Compute our install-time bundle dir
    set(BUNDLE_DIR "${CMAKE_INSTALL_PREFIX}/packages")
    file(MAKE_DIRECTORY "${BUNDLE_DIR}")
    message(STATUS "[install-phase] Bundling into ${BUNDLE_DIR}")

    # Bootstrap pip if missing
    message(STATUS "[install-phase] Bootstrapping pip if needed")
    execute_process(
      COMMAND "$<TARGET_FILE:Python3::Interpreter>" -m ensurepip --default-pip --upgrade
      RESULT_VARIABLE _ep_status
      OUTPUT_VARIABLE  _ep_out
      ERROR_VARIABLE   _ep_err
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    message(STATUS "[install-phase] ensurepip exit: ${_ep_status}")
    message(STATUS "[install-phase] ensurepip stdout:\n${_ep_out}")
    message(STATUS "[install-phase] ensurepip stderr:\n${_ep_err}")

    # Upgrade pip & setuptools just in case
    message(STATUS "[install-phase] Upgrading pip and setuptools")
    execute_process(
      COMMAND "$<TARGET_FILE:Python3::Interpreter>" -m pip install --upgrade pip setuptools wheel
      RESULT_VARIABLE _up_status
      OUTPUT_VARIABLE  _up_out
      ERROR_VARIABLE   _up_err
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    message(STATUS "[install-phase] pip upgrade exit: ${_up_status}")
    message(STATUS "[install-phase] pip upgrade stdout:\n${_up_out}")
    message(STATUS "[install-phase] pip upgrade stderr:\n${_up_err}")

    # Install your requirements
    message(STATUS "[install-phase] Installing requirements.txt")
    execute_process(
      COMMAND "$<TARGET_FILE:Python3::Interpreter>" -m pip install --upgrade
              --target "${BUNDLE_DIR}"
              --requirement "${REQUIREMENTS_FILE}"
      RESULT_VARIABLE _pip_status
      OUTPUT_VARIABLE  _pip_out
      ERROR_VARIABLE   _pip_err
      OUTPUT_STRIP_TRAILING_WHITESPACE
    )
    message(STATUS "[install-phase] pip install exit: ${_pip_status}")
    message(STATUS "[install-phase] pip install stdout:\n${_pip_out}")
    message(STATUS "[install-phase] pip install stderr:\n${_pip_err}")

    if (NOT _pip_status EQUAL 0)
      message(FATAL_ERROR "pip install failed (exit ${_pip_status})")
    endif()
  ]])
endif()


# ───────────────────────────────────────────────────────────
# install Python module
# ───────────────────────────────────────────────────────────
if (INSTALL_MODULE)
    message(STATUS "[App] [*] Install main module")

    install(CODE [[
        message(STATUS "Cleaning existing Python module at ${CMAKE_INSTALL_PREFIX}/lib/ExpenseTracker")
        file(REMOVE_RECURSE "${CMAKE_INSTALL_PREFIX}/lib/ExpenseTracker")
        file(MAKE_DIRECTORY  "${CMAKE_INSTALL_PREFIX}/lib")
    ]])
    install(DIRECTORY "${CMAKE_SOURCE_DIR}/../ExpenseTracker"
        DESTINATION lib
        PATTERN "__pycache__" EXCLUDE
        PATTERN "*.pyc" EXCLUDE
    )
endif()



# ───────────────────────────────────────────────────────────
# install Python dist (external script)
# ───────────────────────────────────────────────────────────
if(INSTALL_STDLIB)
  message(STATUS "[App] [*] Python dist")

  # Select interpreter once
  find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

  # Configure the install-time script
  configure_file(
      ${CMAKE_SOURCE_DIR}/cmake/install_python_dist.cmake.in
      ${CMAKE_BINARY_DIR}/install_python_dist.cmake
      @ONLY)                   # only @VAR@ placeholders, keep ${...}

  # Run it during `cmake --install`
  install(SCRIPT "${CMAKE_BINARY_DIR}/install_python_dist.cmake")
endif()
    

# ───────────────────────────────────────────────────────────
# legal documents
# ───────────────────────────────────────────────────────────
install(FILES "${CMAKE_SOURCE_DIR}/../LICENSE" DESTINATION .)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/legal/" DESTINATION "legal")

# ───────────────────────────────────────────────────────────
# tests
# ───────────────────────────────────────────────────────────
if(BUILD_TESTS)
    enable_testing()
    # add_subdirectory(tests)  # if/when you have tests/
endif()
