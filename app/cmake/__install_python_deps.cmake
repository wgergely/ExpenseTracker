# cmake/install_python_deps.cmake

# 1) Compute the key paths at install time
set(REQUIREMENTS_FILE "${CMAKE_SOURCE_DIR}/../requirements.txt")
if (NOT EXISTS "${REQUIREMENTS_FILE}")
  message(FATAL_ERROR "Python requirements file not found: ${REQUIREMENTS_FILE}")
endif()

set(BUNDLE_DIR "${CMAKE_INSTALL_PREFIX}/packages")
file(MAKE_DIRECTORY "${BUNDLE_DIR}")

# 2) Convert everything to native Windows paths
file(TO_NATIVE_PATH "${Python3_EXECUTABLE}"   _py_exe)
file(TO_NATIVE_PATH "${REQUIREMENTS_FILE}"    _req_file)
file(TO_NATIVE_PATH "${BUNDLE_DIR}"           _bundle_dir)

message(STATUS "[install-phase] Using Python:      ${_py_exe}")
message(STATUS "[install-phase] requirements.txt: ${_req_file}")
message(STATUS "[install-phase] bundling into:   ${_bundle_dir}")

# 3) Run pip with each option as a separate argument
execute_process(
  COMMAND 
    "${_py_exe}"
    "-m" "pip" "install" "--upgrade"
    "--target"   "${_bundle_dir}"
    "--requirement" "${_req_file}"
  RESULT_VARIABLE   _pip_status
  OUTPUT_VARIABLE   _pip_out
  ERROR_VARIABLE    _pip_err
  OUTPUT_STRIP_TRAILING_WHITESPACE
)

# 4) Show everything—even on success
message(STATUS "[install-phase] pip exit code: ${_pip_status}")
message(STATUS "[install-phase] pip stdout:\n${_pip_out}")
message(STATUS "[install-phase] pip stderr:\n${_pip_err}")

# 5) Fail if pip returned a non-zero code
if (NOT _pip_status EQUAL 0)
  message(FATAL_ERROR "pip install failed (exit ${_pip_status})")
endif()
