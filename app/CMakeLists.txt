# ./app/CMakeLists.txt

cmake_minimum_required(VERSION 3.31)
cmake_policy(VERSION 3.31)
cmake_policy(SET CMP0077 NEW)


# ───────────────────────────────────────────────────────────
# global settings
# ───────────────────────────────────────────────────────────
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_POSITION_INDEPENDENT_CODE ON)   # useful for static libs / shared code
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# default to Release unless user says otherwise
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE "Release" CACHE STRING "Build type" FORCE)
endif()


set(App_VERSION "0.0.0" CACHE STRING "App version")
string(TIMESTAMP CURRENT_YEAR "%Y" UTC)

message(STATUS "[App] Version ........: ${App_VERSION}")
message(STATUS "[App] Build type .....: ${CMAKE_BUILD_TYPE}")
message(STATUS "[App] Generator ......: ${CMAKE_GENERATOR}")


# ───────────────────────────────────────────────────────────
# build options
# ───────────────────────────────────────────────────────────
option(USE_VCPKG                "Use vcpkg for dependencies"        ON)
option(BUILD_PYTHON_INTERPRETER "Build python interpreter"          ON)
option(BUILD_PYTHON_LAUNCHER    "Build main executable"             ON)
option(INSTALL_REQUIREMENTS     "Install python requirements"       ON)
option(INSTALL_MODULE           "Install main python module"        ON)
option(INSTALL_PYTHONLIBS       "Install standard Python libraries" ON)


foreach(opt
USE_VCPKG
BUILD_PYTHON_INTERPRETER
BUILD_PYTHON_LAUNCHER
INSTALL_REQUIREMENTS
INSTALL_MODULE
INSTALL_PYTHONLIBS
)
set(${opt} "${${opt}}" CACHE BOOL " ")
endforeach()

message(STATUS "[Options]")
foreach(opt
USE_VCPKG
BUILD_PYTHON_INTERPRETER
BUILD_PYTHON_LAUNCHER
INSTALL_REQUIREMENTS
INSTALL_MODULE
        INSTALL_PYTHONLIBS
        )
        message(STATUS "  - ${opt}: ${${opt}}")
        endforeach()


# ───────────────────────────────────────────────────────────
# vcpkg integration
# ───────────────────────────────────────────────────────────
if(USE_VCPKG)
    include(cmake/vcpkg-bootstrap.cmake)
endif()

project(ExpenseTracker VERSION ${App_VERSION} LANGUAGES CXX)
        
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
endif()



# ───────────────────────────────────────────────────────────
# ExpenseTracker launcher stub
# ───────────────────────────────────────────────────────────
if(BUILD_PYTHON_LAUNCHER)
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

    if(MSVC AND WIN32)
        target_link_options(PyLauncher PRIVATE "/MANIFESTFILE:${CMAKE_CURRENT_SOURCE_DIR}/rsc/app.manifest")
    endif()

    set_target_properties(PyLauncher PROPERTIES OUTPUT_NAME "${PROJECT_NAME}")
    
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
endif()



# ───────────────────────────────────────────────────────────
# Python requirements
# ───────────────────────────────────────────────────────────
if (INSTALL_REQUIREMENTS)      
  find_package(Python3 REQUIRED COMPONENTS Interpreter)

    # configure copy the requirements file on configure time
    configure_file(
        "${CMAKE_SOURCE_DIR}/cmake/install_requirements.cmake.in"
        "${CMAKE_BINARY_DIR}/install_requirements.cmake"
        @ONLY
      )
    install(SCRIPT "${CMAKE_BINARY_DIR}/install_requirements.cmake")
endif()


# ───────────────────────────────────────────────────────────
# install Python module
# ───────────────────────────────────────────────────────────
if (INSTALL_MODULE)
    configure_file(
        ${CMAKE_SOURCE_DIR}/cmake/install_module.cmake.in
        ${CMAKE_BINARY_DIR}/install_module.cmake
        @ONLY
    )
    install(SCRIPT "${CMAKE_BINARY_DIR}/install_module.cmake")
endif()



# ───────────────────────────────────────────────────────────
# install Python built-int libraries
# ───────────────────────────────────────────────────────────
if(INSTALL_PYTHONLIBS)
  # Select interpreter once
  find_package(Python3 REQUIRED COMPONENTS Interpreter Development)

  # Configure the install-time script
  configure_file(
      ${CMAKE_SOURCE_DIR}/cmake/install_python_dist.cmake.in
      ${CMAKE_BINARY_DIR}/install_python_dist.cmake
      @ONLY)

  install(SCRIPT "${CMAKE_BINARY_DIR}/install_python_dist.cmake")
endif()
    

# ───────────────────────────────────────────────────────────
# legal documents
# ───────────────────────────────────────────────────────────
install(FILES "${CMAKE_SOURCE_DIR}/../LICENSE" DESTINATION .)
install(DIRECTORY "${CMAKE_SOURCE_DIR}/legal/" DESTINATION .)



# ───────────────────────────────────────────────────────────
# Intaller
# ───────────────────────────────────────────────────────────
include(cmake/installer.cmake)