// PythonInterpreter.cpp
#define PY_SSIZE_T_CLEAN
#include <Python.h>

#include <filesystem>
#include <iostream>
#include <vector>
#include <sstream>

#include "dist.h"


// ────────────────────────────────────────────────────────────
// helpers
// ────────────────────────────────────────────────────────────
namespace
{
    [[nodiscard]]
    bool push_search_path(PyConfig& c, const std::filesystem::path& p)
    {
        const PyStatus st{PyWideStringList_Append(&c.module_search_paths,
                                                  p.wstring().c_str())};
        if (PyStatus_Exception(st))
        {
            Py_ExitStatusException(st);
            return false;
        }
        return true;
    }

#ifndef _WIN32
    std::vector<std::wstring>         wargv_store;
    std::vector<wchar_t*> convert_argv(int argc, char* argv[])
    {
        wargv_store.reserve(argc);
        std::vector<wchar_t*> out;
        out.reserve(argc);
        for (int i = 0; i < argc; ++i)
        {
            wargv_store.emplace_back(std::filesystem::path{argv[i]}.wstring());
            out.push_back(wargv_store.back().data());
        }
        return out;
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
    // load bundle layout and environment
    const auto paths = dist::get_paths();
    if (!dist::LoadEnvironment(paths))
        return 1;

    // ───────── configure interpreter in isolated mode ─────────
    PyConfig cfg;
    PyConfig_InitIsolatedConfig(&cfg);

    cfg.module_search_paths_set = 1;
    cfg.interactive             = 1;
    cfg.user_site_directory     = 0;
    cfg.use_environment         = 0;   // ignore ALL external env vars
    cfg.safe_path               = 1;
    cfg.install_signal_handlers = 1;

    const auto root = paths.bin_dir.parent_path();

    if (PyStatus_Exception(PyConfig_SetString(&cfg, &cfg.home,        paths.bin_dir.wstring().c_str())) ||
        PyStatus_Exception(PyConfig_SetString(&cfg, &cfg.prefix,      root.wstring().c_str()))         ||
        PyStatus_Exception(PyConfig_SetString(&cfg, &cfg.base_prefix, root.wstring().c_str())))
        Py_ExitStatusException(PyStatus{});

    push_search_path(cfg, paths.module_dir);
    push_search_path(cfg, paths.sitepackages_dir);
    push_search_path(cfg, paths.bin_dir);
    push_search_path(cfg, paths.py_zip);

#ifdef _WIN32
    if (PyStatus_Exception(PyConfig_SetArgv(&cfg, argc, argv)))
        Py_ExitStatusException(PyStatus{});
#else
    auto wargv = convert_argv(argc, argv);
    if (PyStatus_Exception(PyConfig_SetArgv(&cfg, argc, wargv.data())))
        Py_ExitStatusException(PyStatus{});
#endif

    if (PyStatus_Exception(Py_InitializeFromConfig(&cfg)))
        Py_ExitStatusException(PyStatus{});

    PyConfig_Clear(&cfg);

#ifdef _WIN32
    return Py_Main(argc, argv);
#else
    return Py_Main(argc, wargv.data());
#endif
}
