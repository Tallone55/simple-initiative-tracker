/* Minimal native launcher for the portable Windows build. Sets up
 * the DLL search path and GI_TYPELIB_PATH/GSETTINGS_SCHEMA_DIR
 * environment variables, then execs the bundled pythonw.exe against
 * bin\sit.py -- giving a single double-clickable
 * SimpleInitiativeTracker.exe with no arguments required.
 *
 * DLL search path is set via PATH, not SetDllDirectoryW: that API
 * only affects the calling process's own search path, not a child
 * process started via CreateProcessW, so pythonw.exe would never
 * see it and would fail to load GTK4's DLLs from runtime\lib.
 * Environment variables set with SetEnvironmentVariableW *are*
 * inherited by the child, so PATH is what actually has to carry
 * runtime\lib.
 *
 * pythonw.exe has no console, so a Python-level startup failure
 * (e.g. a missing DLL) is otherwise completely silent -- both
 * stdout and stderr are redirected to a log file next to this
 * executable, and this launcher waits briefly for the child to
 * report back: if it exits within that window with a nonzero code,
 * that's treated as a startup failure and reported via a message
 * box pointing at the log; if it's still running after the window,
 * it's assumed to have started successfully and the launcher exits,
 * leaving the app running on its own.
 */
#include <windows.h>
#include <shlwapi.h>
#include <stdio.h>

#define STARTUP_WAIT_MS 4000

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrevInst, PWSTR cmdline, int nShowCmd) {
    wchar_t base_dir[MAX_PATH];
    if (GetModuleFileNameW(NULL, base_dir, MAX_PATH) == 0) {
        MessageBoxW(NULL, L"Could not determine the application's own location.",
                    L"Simple Initiative Tracker", MB_OK | MB_ICONERROR);
        return 1;
    }
    PathRemoveFileSpecW(base_dir);

    wchar_t dll_dir[MAX_PATH];
    _snwprintf(dll_dir, MAX_PATH, L"%s\\runtime\\lib", base_dir);

    wchar_t existing_path[MAX_PATH];
    DWORD existing_len = GetEnvironmentVariableW(L"PATH", existing_path, MAX_PATH);
    if (existing_len == 0 || existing_len >= MAX_PATH) {
        existing_path[0] = L'\0';
    }
    wchar_t combined_path[MAX_PATH * 2];
    _snwprintf(combined_path, MAX_PATH * 2, L"%s;%s", dll_dir, existing_path);
    SetEnvironmentVariableW(L"PATH", combined_path);

    wchar_t typelib_dir[MAX_PATH];
    _snwprintf(typelib_dir, MAX_PATH, L"%s\\runtime\\lib\\girepository-1.0", base_dir);
    SetEnvironmentVariableW(L"GI_TYPELIB_PATH", typelib_dir);

    wchar_t schema_dir[MAX_PATH];
    _snwprintf(schema_dir, MAX_PATH, L"%s\\runtime\\share\\glib-2.0\\schemas", base_dir);
    SetEnvironmentVariableW(L"GSETTINGS_SCHEMA_DIR", schema_dir);

    wchar_t data_dirs[MAX_PATH];
    _snwprintf(data_dirs, MAX_PATH, L"%s\\runtime\\share", base_dir);
    SetEnvironmentVariableW(L"XDG_DATA_DIRS", data_dirs);

    /* Regenerated fresh every run, matching the macOS and Linux
     * portable launchers: the cache gdk-pixbuf-query-loaders.exe
     * produces embeds absolute paths, which only match wherever this
     * copy happens to have been extracted to, not wherever it was
     * built. Without this, gdk-pixbuf has no way to discover any
     * loader plugin at all -- SVG included, which is what the About
     * dialog's own icon needs -- since neither a relocatable cache
     * nor GDK_PIXBUF_MODULE_FILE otherwise ever gets set up on
     * Windows at all. Best-effort: if this fails for any reason, the
     * app still launches, just without pixbuf-loader-dependent image
     * support (this matches how build_windows.sh already treats a
     * missing pixbuf loader directory as a hard build-time error, but
     * a failure to regenerate the cache at *launch* time on some
     * particular machine shouldn't block the app from opening at
     * all).
     */
    wchar_t loaders_glob[MAX_PATH];
    _snwprintf(loaders_glob, MAX_PATH, L"%s\\runtime\\lib\\gdk-pixbuf-2.0\\loaders\\*.dll", base_dir);

    wchar_t query_loaders_exe[MAX_PATH];
    _snwprintf(query_loaders_exe, MAX_PATH, L"%s\\runtime\\lib\\gdk-pixbuf-2.0\\gdk-pixbuf-query-loaders.exe", base_dir);

    wchar_t pixbuf_cache[MAX_PATH];
    _snwprintf(pixbuf_cache, MAX_PATH, L"%s\\runtime\\lib\\gdk-pixbuf-2.0\\loaders.cache.runtime", base_dir);

    wchar_t query_command[MAX_PATH * 2];
    _snwprintf(query_command, MAX_PATH * 2, L"\"%s\" \"%s\"", query_loaders_exe, loaders_glob);

    SECURITY_ATTRIBUTES cache_sa;
    ZeroMemory(&cache_sa, sizeof(cache_sa));
    cache_sa.nLength = sizeof(cache_sa);
    cache_sa.bInheritHandle = TRUE;

    HANDLE cache_out = CreateFileW(
        pixbuf_cache, GENERIC_WRITE, FILE_SHARE_READ, &cache_sa,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL
    );
    HANDLE cache_err = CreateFileW(
        L"NUL", GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, &cache_sa,
        OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL
    );

    if (cache_out != INVALID_HANDLE_VALUE) {
        STARTUPINFOW query_si;
        ZeroMemory(&query_si, sizeof(query_si));
        query_si.cb = sizeof(query_si);
        query_si.dwFlags |= STARTF_USESTDHANDLES;
        query_si.hStdOutput = cache_out;
        query_si.hStdError = (cache_err != INVALID_HANDLE_VALUE) ? cache_err : cache_out;

        PROCESS_INFORMATION query_pi;
        ZeroMemory(&query_pi, sizeof(query_pi));

        if (CreateProcessW(NULL, query_command, NULL, NULL, TRUE, 0, NULL, base_dir, &query_si, &query_pi)) {
            WaitForSingleObject(query_pi.hProcess, 5000);
            CloseHandle(query_pi.hProcess);
            CloseHandle(query_pi.hThread);
            SetEnvironmentVariableW(L"GDK_PIXBUF_MODULE_FILE", pixbuf_cache);
        }
        CloseHandle(cache_out);
        if (cache_err != INVALID_HANDLE_VALUE) {
            CloseHandle(cache_err);
        }
    }

    wchar_t python_exe[MAX_PATH];
    _snwprintf(python_exe, MAX_PATH, L"%s\\runtime\\python\\pythonw.exe", base_dir);

    wchar_t script[MAX_PATH];
    _snwprintf(script, MAX_PATH, L"%s\\bin\\sit.py", base_dir);

    wchar_t command[MAX_PATH * 2 + 1024];
    if (cmdline && cmdline[0] != L'\0') {
        /* cmdline is whatever the launching process passed after the
         * program name -- a file path from "Open With", a file
         * manager association, or a drag-and-drop -- already in
         * command-line form (quoted as needed by whatever invoked
         * this launcher), so it's appended as-is. */
        _snwprintf(command, MAX_PATH * 2 + 1024, L"\"%s\" \"%s\" %s", python_exe, script, cmdline);
    } else {
        _snwprintf(command, MAX_PATH * 2 + 1024, L"\"%s\" \"%s\"", python_exe, script);
    }

    wchar_t log_path[MAX_PATH];
    _snwprintf(log_path, MAX_PATH, L"%s\\sit_error.log", base_dir);

    SECURITY_ATTRIBUTES sa;
    ZeroMemory(&sa, sizeof(sa));
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE log_handle = CreateFileW(
        log_path, GENERIC_WRITE, FILE_SHARE_READ, &sa,
        CREATE_ALWAYS, FILE_ATTRIBUTE_NORMAL, NULL
    );

    STARTUPINFOW si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    if (log_handle != INVALID_HANDLE_VALUE) {
        si.dwFlags |= STARTF_USESTDHANDLES;
        si.hStdOutput = log_handle;
        si.hStdError = log_handle;
    }
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    BOOL created = CreateProcessW(
        NULL, command, NULL, NULL, /* bInheritHandles */ TRUE,
        0, NULL, base_dir, &si, &pi
    );
    if (log_handle != INVALID_HANDLE_VALUE) {
        CloseHandle(log_handle);
    }
    if (!created) {
        MessageBoxW(NULL, L"Failed to launch Simple Initiative Tracker.",
                    L"Simple Initiative Tracker", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);

    DWORD wait_result = WaitForSingleObject(pi.hProcess, STARTUP_WAIT_MS);
    if (wait_result == WAIT_OBJECT_0) {
        DWORD exit_code = 0;
        GetExitCodeProcess(pi.hProcess, &exit_code);
        CloseHandle(pi.hProcess);
        if (exit_code != 0) {
            wchar_t message[MAX_PATH + 256];
            _snwprintf(message, MAX_PATH + 256,
                L"Simple Initiative Tracker exited unexpectedly (code %lu).\n\n"
                L"Details were written to:\n%s",
                exit_code, log_path);
            MessageBoxW(NULL, message, L"Simple Initiative Tracker", MB_OK | MB_ICONERROR);
            return 1;
        }
        return 0;
    }

    CloseHandle(pi.hProcess);
    return 0;
}
