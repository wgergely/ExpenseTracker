// PythonInterpreter.cpp
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <filesystem>
#include <vector>

#include "dist.h"

#ifdef _WIN32
    #include <windows.h>
    // build as a windowed executable with a Unicode entry point
    #pragma comment(linker, "/SUBSYSTEM:windows /ENTRY:wmainCRTStartup")
#endif

// ────────────────────────────────────────────────────────────
// helpers
// ────────────────────────────────────────────────────────────
namespace
{
    void push_search_path(PyConfig& cfg, const std::filesystem::path& p)
    {
        const PyStatus st{PyWideStringList_Append(&cfg.module_search_paths,
                                                  p.wstring().c_str())};
        if (PyStatus_Exception(st))
            Py_ExitStatusException(st);      // aborts – no further code runs
    }

#ifndef _WIN32
    /** Convert char argv to wchar_t** without leaking. */
    std::vector<wchar_t*> convert_argv(int argc,
                                       char* argv[],
                                       std::vector<std::wstring>& store)
    {
        store.reserve(static_cast<std::size_t>(argc));
        std::vector<wchar_t*> out;
        out.reserve(static_cast<std::size_t>(argc));
        for (int i = 0; i < argc; ++i)
        {
            store.emplace_back(std::filesystem::path{argv[i]}.wstring());
            out.push_back(store.back().data());
        }
        return out;                          // points into store (same lifetime)
    }
#endif
} // namespace

// ────────────────────────────────────────────────────────────
// require Python ≥ 3.11
// ────────────────────────────────────────────────────────────
#if (PY_VERSION_HEX < 0x030B0000)
#   error "Python 3.11 or newer is required"
#endif

// ────────────────────────────────────────────────────────────
// program entry
// ────────────────────────────────────────────────────────────
#ifdef _WIN32
int wmain(int argc, wchar_t* argv[])
#else
int main(int argc, char* argv[])
#endif
{
    // locate bundle – aborts with GUI message-box if anything is missing
    const auto paths = dist::get_paths();
    if (!dist::LoadEnvironment(paths))
        return 1;

    const auto root = paths.bin_dir.parent_path();   // <— needed below

    // ───────── configure interpreter in isolated mode ─────────
    PyConfig cfg;
    PyConfig_InitIsolatedConfig(&cfg);

    cfg.module_search_paths_set = 1;
    cfg.interactive             = 0;
    cfg.user_site_directory     = 0;
    cfg.use_environment         = 0;   // ignore external env vars
    cfg.safe_path               = 1;
    cfg.install_signal_handlers = 1;
    cfg.optimization_level      = 2;   // run with -OO (strip doc-strings)

    if (PyStatus_Exception(PyConfig_SetString(&cfg, &cfg.home,        paths.bin_dir.wstring().c_str())) ||
        PyStatus_Exception(PyConfig_SetString(&cfg, &cfg.prefix,      root.wstring().c_str()))         ||
        PyStatus_Exception(PyConfig_SetString(&cfg, &cfg.base_prefix, root.wstring().c_str())))
        Py_ExitStatusException(PyStatus{});

    push_search_path(cfg, paths.module_dir);
    push_search_path(cfg, paths.sitepackages_dir);
    push_search_path(cfg, paths.bin_dir);
    push_search_path(cfg, paths.py_zip);           // zipimport-able std-lib

    // execute embedded command “import ExpenseTracker; ExpenseTracker.exec_()”
    if (PyStatus_Exception(PyConfig_SetString(&cfg,
                                              &cfg.run_command,
                                              dist::PY_EXEC_CMD.c_str())))
        Py_ExitStatusException(PyStatus{});

#ifdef _WIN32
    if (PyStatus_Exception(PyConfig_SetArgv(&cfg, argc, argv)))
        Py_ExitStatusException(PyStatus{});
#else
    std::vector<std::wstring> wargv_store;            // freed when main returns
    auto wargv = convert_argv(argc, argv, wargv_store);
    if (PyStatus_Exception(PyConfig_SetArgv(&cfg, argc, wargv.data())))
        Py_ExitStatusException(PyStatus{});
#endif

    if (PyStatus_Exception(Py_InitializeFromConfig(&cfg)))
        Py_ExitStatusException(PyStatus{});

    PyConfig_Clear(&cfg);   // release all memory owned by cfg

    // ───────── run the command (ExpenseTracker.exec_()) ────────
    const int rc = Py_RunMain();
    if (rc != 0)
    {
#ifdef _WIN32
        MessageBoxW(nullptr,
                    L"Python reported a fatal error while executing ExpenseTracker.",
                    L"Error", MB_ICONERROR | MB_OK);
#else
        // GUI-only build on non-Windows still prints to std-err for logging.
        std::wcerr << L"Python exited with status " << rc << L'\n';
#endif
    }
    return rc;   // OS reclaims everything else – no leaks at runtime
}
