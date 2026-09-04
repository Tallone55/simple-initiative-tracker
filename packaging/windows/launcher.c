/* Minimal native launcher for the portable Windows build. Sets up
 * the DLL search directory and GI_TYPELIB_PATH/GSETTINGS_SCHEMA_DIR
 * environment variables, then execs the bundled pythonw.exe against
 * bin\sit.py -- giving a single double-clickable
 * SimpleInitiativeTracker.exe with no arguments required.
 */
#include <windows.h>
#include <shlwapi.h>
#include <stdio.h>

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
    SetDllDirectoryW(dll_dir);

    wchar_t typelib_dir[MAX_PATH];
    _snwprintf(typelib_dir, MAX_PATH, L"%s\\runtime\\lib\\girepository-1.0", base_dir);
    SetEnvironmentVariableW(L"GI_TYPELIB_PATH", typelib_dir);

    wchar_t schema_dir[MAX_PATH];
    _snwprintf(schema_dir, MAX_PATH, L"%s\\runtime\\share\\glib-2.0\\schemas", base_dir);
    SetEnvironmentVariableW(L"GSETTINGS_SCHEMA_DIR", schema_dir);

    wchar_t data_dirs[MAX_PATH];
    _snwprintf(data_dirs, MAX_PATH, L"%s\\runtime\\share", base_dir);
    SetEnvironmentVariableW(L"XDG_DATA_DIRS", data_dirs);

    wchar_t python_exe[MAX_PATH];
    _snwprintf(python_exe, MAX_PATH, L"%s\\runtime\\python\\pythonw.exe", base_dir);

    wchar_t script[MAX_PATH];
    _snwprintf(script, MAX_PATH, L"%s\\bin\\sit.py", base_dir);

    wchar_t command[MAX_PATH * 2];
    _snwprintf(command, MAX_PATH * 2, L"\"%s\" \"%s\"", python_exe, script);

    STARTUPINFOW si;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi;
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(NULL, command, NULL, NULL, FALSE, 0, NULL, base_dir, &si, &pi)) {
        MessageBoxW(NULL, L"Failed to launch Simple Initiative Tracker.",
                    L"Simple Initiative Tracker", MB_OK | MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
