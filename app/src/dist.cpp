// dist.cpp
#include "dist.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#endif

namespace dist
{
    // ────────────────────────────────────────────────────────────
    // helpers
    // ────────────────────────────────────────────────────────────
    std::filesystem::path get_executable_dir()
    {
#ifdef _WIN32
        wchar_t buffer[MAX_PATH];
        DWORD len = ::GetModuleFileNameW(nullptr, buffer, MAX_PATH);
        if (!len || len == MAX_PATH)
            throw std::runtime_error("GetModuleFileNameW failed");
        return std::filesystem::path(buffer).remove_filename();
#else
        char buffer[1024];
        ssize_t len = ::readlink("/proc/self/exe", buffer, sizeof(buffer) - 1);
        if (len == -1)
            throw std::runtime_error("readlink(\"/proc/self/exe\") failed");
        buffer[len] = '\0';
        return std::filesystem::path(buffer).remove_filename();
#endif
    }

    Paths get_paths()
    {
        const auto exe_dir = get_executable_dir();
        const auto root = exe_dir.parent_path();

        return {
            root / BIN_DIR,
            root / MODULE_DIR,
            root / SITEPACKAGES_DIR,
            root / APP_LAUNCHER_BIN,
            root / PY_INTERPRETER_BIN,
            root / PY_ZIP};
    }

    bool LoadEnvironment(const Paths &paths)
    {
        const auto report = [&](const std::wstring &msg)
        {
#ifdef _WIN32
            MessageBoxW(nullptr, msg.c_str(), L"Error", MB_ICONERROR | MB_OK);
#endif
            std::wcerr << L"Error: " << msg << L'\n';
        };

        // directory sanity
        for (const auto &d : {paths.bin_dir, paths.module_dir, paths.sitepackages_dir})
            if (!std::filesystem::is_directory(d))
                return report(L"Required directory missing:\n" + d.wstring()), false;

        // file sanity
        for (const auto &f : {paths.app_launcher_bin,
                              paths.py_interpreter_bin})
            if (!std::filesystem::is_regular_file(f))
                return report(L"Required file missing:\n" + f.wstring()), false;

// ───────── windows env ──────────────────────────────────────
#ifdef _WIN32
        ::SetDllDirectoryW(paths.bin_dir.wstring().c_str());
        ::AddDllDirectory(paths.bin_dir.wstring().c_str());

        ::SetEnvironmentVariableW(L"PYTHONHOME", paths.bin_dir.wstring().c_str());
        const std::wstring pyPath = paths.module_dir.wstring() + L';' + paths.sitepackages_dir.wstring();
        ::SetEnvironmentVariableW(L"PYTHONPATH", pyPath.c_str());

        wchar_t *oldPath = nullptr;
        size_t len = 0;
        _wdupenv_s(&oldPath, &len, L"PATH");
        const std::wstring newPath = paths.bin_dir.wstring() + L';' + (oldPath ? oldPath : L"");
        if (oldPath)
            free(oldPath);
        ::SetEnvironmentVariableW(L"PATH", newPath.c_str());

// ───────── posix env ───────────────────────────────────────
#else
        setenv("PYTHONHOME", paths.bin_dir.string().c_str(), 1);
        const std::string pyPath = paths.module_dir.string() + ':' + paths.sitepackages_dir.string();
        setenv("PYTHONPATH", pyPath.c_str(), 1);

        const char *oldPath = std::getenv("PATH");
        std::string newPath = paths.bin_dir.string();
        if (oldPath)
            newPath += ':' + std::string(oldPath);
        setenv("PATH", newPath.c_str(), 1);
#endif

        return true;
    }

// ────────────────────────────────────────────────────────────
// process launcher
// ────────────────────────────────────────────────────────────
#ifdef _WIN32
    int launch_process(int argc, wchar_t *argv[], const std::filesystem::path &exe)
#else
    int launch_process(int argc, char *argv[], const std::filesystem::path &exe)
#endif
    {
#ifdef _WIN32
        if (exe.empty() || !std::filesystem::is_regular_file(exe))
        {
            const std::wstring msg = L"Error: " + exe.wstring() + L" not found.";
            MessageBoxW(nullptr, msg.c_str(), L"Error", MB_ICONERROR | MB_OK);
            std::wcerr << msg << L'\n';
            return 1;
        }

        std::wstring cmd = exe.wstring();
        for (int i = 1; i < argc; ++i)
        {
            cmd.push_back(L' ');
            cmd.append(argv[i]);
        }

        STARTUPINFOW si{};
        si.cb = sizeof si;
        PROCESS_INFORMATION pi{};
        if (!CreateProcessW(nullptr, cmd.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi))
        {
            const std::wstring msg = L"CreateProcess failed (" + std::to_wstring(GetLastError()) + L")";
            MessageBoxW(nullptr, msg.c_str(), L"Error", MB_ICONERROR | MB_OK);
            std::wcerr << msg << L'\n';
            return 1;
        }

        WaitForSingleObject(pi.hProcess, INFINITE);
        CloseHandle(pi.hProcess);
        CloseHandle(pi.hThread);
        return 0;

// ───────── posix fallback ──────────────────────────────────
#else
        if (exe.empty() || !std::filesystem::is_regular_file(exe))
        {
            std::cerr << "Error: " << exe << " not found.\n";
            return 1;
        }

        std::string cmd = exe.string();
        for (int i = 1; i < argc; ++i)
        {
            cmd.push_back(' ');
            cmd += argv[i];
        }

        return std::system(cmd.c_str());
#endif
    }

} // namespace dist
