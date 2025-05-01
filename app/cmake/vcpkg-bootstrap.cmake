# app/cmake/vcpkg-bootstrap.cmake
cmake_minimum_required(VERSION 3.24)

if(DEFINED VCPKG_BOOTSTRAPPED)
    return()
endif()
set(VCPKG_BOOTSTRAPPED TRUE)

include(FetchContent)

# ───── user knobs ────────────────────────────────────────────
set(VCPKG_TAG "2025.04.09" CACHE STRING "vcpkg commit / tag")

if(NOT DEFINED VCPKG_ROOT OR VCPKG_ROOT STREQUAL "")
    set(VCPKG_ROOT "${CMAKE_BINARY_DIR}/_deps/vcpkg-src" CACHE PATH
        "Where vcpkg is be cloned to" FORCE)
endif()

message(STATUS "[vcpkg] Root .................: ${VCPKG_ROOT}")
message(STATUS "[vcpkg] Commit / tag .........: ${VCPKG_TAG}")

# ───── UNC guard (Windows) ───────────────────────────────────
if(WIN32 AND VCPKG_ROOT MATCHES "^[/\\\\]{2}[^/\\\\]+[/\\\\]")
    message(FATAL_ERROR
        "[vcpkg] '${VCPKG_ROOT}' is on a network share (UNC path).\n"
        "Clone to a local drive or pass -DVCPKG_ROOT=C:/vcpkg.")
endif()

# ───── ensure Git and safe.directory ─────────────────────────
message(STATUS "[vcpkg] Checking Git …")
find_program(GIT_EXECUTABLE git REQUIRED)
if(NOT GIT_EXECUTABLE)
    message(FATAL_ERROR "[vcpkg] Git not found")
endif()

message(STATUS "[vcpkg] Adding safe.directory …")
execute_process(
    COMMAND "${GIT_EXECUTABLE}" config --global --add safe.directory "${VCPKG_ROOT}"
    OUTPUT_QUIET ERROR_QUIET)

# ───── clean half-clones ─────────────────────────────────────
if(EXISTS "${VCPKG_ROOT}" AND NOT EXISTS "${VCPKG_ROOT}/.git")
    message(WARNING "[vcpkg] Removing incomplete directory: ${VCPKG_ROOT}")
    file(REMOVE_RECURSE "${VCPKG_ROOT}")
endif()

# ───── FetchContent clone ────────────────────────────────────
message(STATUS "[vcpkg] Cloning …")
FetchContent_Declare(
    vcpkg
    GIT_REPOSITORY https://github.com/microsoft/vcpkg.git
    GIT_TAG        ${VCPKG_TAG}
    GIT_SHALLOW    TRUE
    SOURCE_DIR     ${VCPKG_ROOT})
FetchContent_Populate(vcpkg)

# mark repo safe locally (harmless if already set)
execute_process(
    COMMAND "${GIT_EXECUTABLE}" -C "${VCPKG_ROOT}" config --local safe.directory "${VCPKG_ROOT}"
    OUTPUT_QUIET ERROR_QUIET)

# ───── bootstrap once ───────────────────────────────────────
set(_vcpkg_exe "${VCPKG_ROOT}/vcpkg${CMAKE_EXECUTABLE_SUFFIX}")
if(NOT EXISTS "${_vcpkg_exe}")
    message(STATUS "[vcpkg] Bootstrapping …")
    if(WIN32)
        # Call the batch file directly; CMake automatically quotes paths.
        execute_process(
            COMMAND "${VCPKG_ROOT}/bootstrap-vcpkg.bat" -disableMetrics
            WORKING_DIRECTORY "${VCPKG_ROOT}"
            RESULT_VARIABLE _boot
            ERROR_VARIABLE  _boot_err)
    else()
        execute_process(
            COMMAND "${VCPKG_ROOT}/bootstrap-vcpkg.sh" -disableMetrics
            WORKING_DIRECTORY "${VCPKG_ROOT}"
            RESULT_VARIABLE _boot
            ERROR_VARIABLE  _boot_err)
    endif()
    if(_boot)
        message(FATAL_ERROR "[vcpkg] bootstrap failed:\n${_boot_err}")
    endif()
else()
    message(STATUS "[vcpkg] Bootstrap skipped (executable already present)")
endif()

# ───── expose tool-chain ─────────────────────────────────────
set(CMAKE_TOOLCHAIN_FILE
    "${VCPKG_ROOT}/scripts/buildsystems/vcpkg.cmake"
    CACHE STRING "vcpkg toolchain")

# ───── enable manifest mode every time this script runs ──────
#  • VCPKG_FEATURE_FLAGS=manifests tells vcpkg to read vcpkg.json
#  • VCPKG_ROOT is already set earlier; export triplet if you want one
set(ENV{VCPKG_FEATURE_FLAGS} "manifests")
if(NOT DEFINED ENV{VCPKG_DEFAULT_TRIPLET})
    # pick one that matches your toolset; change to e.g. x64-windows-static
    set(ENV{VCPKG_DEFAULT_TRIPLET} "x64-windows")
endif()

# you probably still don’t want telemetry
set(ENV{VCPKG_DISABLE_METRICS} 1)

message(STATUS "[vcpkg] READY — using ${VCPKG_ROOT}@${VCPKG_TAG}")

