/* Minimal native launcher for the portable Windows build.
 *
 * A bundled Python interpreter alone can't be the thing the user
 * double-clicks: GI_TYPELIB_PATH, GSETTINGS_SCHEMA_DIR, and the
 * bundle's own DLL directory all need to be set up *before* bin/
 * sit.py's own "import gi" ever runs, and pythonw.exe itself takes
 * no arguments implicitly, so a bare renamed copy of it wouldn't
 * know what script to launch anyway. This tiny compiled stub -- built
 * as part of build_windows.sh, from this file -- sets that
 * environment up, then execs the bundled pythonw.exe against bin\
 * sit.py, giving a single double-clickable SimpleInitiativeTracker.exe
 * with no arguments required. Same role as the shell launcher in the
 * Linux portable bundle and the Info.plist-driven launcher in the
 * macOS .app bundle.
 *
 * SetDllDirectoryW covers GTK4/GLib/etc.'s own DLL-to-DLL
 * dependencies (the Windows loader always searches a directory
 * added this way); GI_TYPELIB_PATH/GSETTINGS_SCHEMA_DIR are read by
 * GObject Introspection/GLib themselves, as environment variables,
 * not resolved via the DLL search path at all, so they're set
 * explicitly here too.
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
    PathRemoveFileSpecW(base_dir);  /* strip "\SimpleInitiativeTracker.exe" -> bundle root */

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
