// dist.h
#ifndef APP_DIST_H
#define APP_DIST_H

#include <filesystem>
#include <string>
#include <string_view>

namespace dist
{
    // ────────────────────────────────────────────────────────────
    // directory layout (relative to bundle root)
    // ────────────────────────────────────────────────────────────
    inline const std::filesystem::path BIN_DIR = "bin";
    inline const std::filesystem::path MODULE_DIR = "lib";
    inline const std::filesystem::path SITEPACKAGES_DIR = "packages";

    // ────────────────────────────────────────────────────────────
    // platform-specific executable extension
    // ────────────────────────────────────────────────────────────
#ifdef _WIN32
    inline constexpr std::string_view EXECUTABLE_EXTENSION = ".exe";
#else
    inline constexpr std::string_view EXECUTABLE_EXTENSION = "";
#endif

    inline std::filesystem::path make_executable(std::string_view stem)
    {
        return std::filesystem::path{std::string{stem} + std::string{EXECUTABLE_EXTENSION}};
    }

    // concrete executables inside BIN_DIR
    inline const std::filesystem::path APP_LAUNCHER_BIN = make_executable("ExpenseTracker");
    inline const std::filesystem::path PY_INTERPRETER_BIN =
#ifdef _WIN32
        make_executable("python");
#else
        make_executable("python");
#endif

    // python-stdlib zip (same on all platforms)
    inline const std::filesystem::path PY_ZIP = "python.zip";

    // command fed to the embedded interpreter
    inline const std::wstring PY_EXEC_CMD = L"import ExpenseTracker;ExpenseTracker.exec_()";

    // bundle description
    struct Paths
    {
        std::filesystem::path bin_dir;
        std::filesystem::path module_dir;
        std::filesystem::path sitepackages_dir;
        std::filesystem::path app_launcher_bin;
        std::filesystem::path py_interpreter_bin;
        std::filesystem::path py_zip;
    };

    // ────────────────────────────────────────────────────────────
    // API
    // ────────────────────────────────────────────────────────────
    [[nodiscard]] std::filesystem::path get_executable_dir();
    [[nodiscard]] Paths get_paths();

    bool LoadEnvironment(const Paths &paths);

#ifdef _WIN32
    int launch_process(int argc, wchar_t *argv[], const std::filesystem::path &exe_path);
#else
    int launch_process(int argc, char *argv[], const std::filesystem::path &exe_path);
#endif

} // namespace dist
#endif // APP_DIST_H
