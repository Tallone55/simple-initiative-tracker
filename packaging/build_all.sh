#!/usr/bin/env bash
# Runs whichever of the four platform build scripts are possible on
# this machine, and reports which ones aren't. No single machine can
# natively produce all four (Windows/macOS/Linux each need their own
# native toolchain) -- for all four from one trigger, use the CI
# workflow instead (.github/workflows/release.yml).
#
# Run from anywhere:
#     ./packaging/build_all.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

BUILT=()
SKIPPED=()
FAILED=()

run_step() {
    local label="$1"
    shift
    echo
    echo "---- $label ----"
    if "$@"; then
        BUILT+=("$label")
    else
        FAILED+=("$label")
    fi
}

case "$(uname -s)" in
    Linux)
        echo "Linux host detected: building .deb and .tar.gz."
        run_step ".deb" "$SCRIPT_DIR/build_deb.sh"
        run_step ".tar.gz (portable)" "$SCRIPT_DIR/build_linux_portable.sh"
        SKIPPED+=(".app -- run build_macos.sh on a macOS machine")
        if [ "${MSYSTEM:-}" = "MINGW64" ]; then
            run_step ".exe" "$SCRIPT_DIR/build_windows.sh"
        else
            SKIPPED+=(".exe -- run build_windows.sh from an MSYS2 MINGW64 shell on Windows")
        fi
        ;;
    Darwin)
        echo "macOS host detected: building .app."
        run_step ".app" "$SCRIPT_DIR/build_macos.sh"
        SKIPPED+=(".deb -- run build_deb.sh on a Linux machine")
        SKIPPED+=(".tar.gz -- run build_linux_portable.sh on a Linux machine")
        SKIPPED+=(".exe -- run build_windows.sh from an MSYS2 MINGW64 shell on Windows")
        ;;
    MINGW*|MSYS*)
        if [ "${MSYSTEM:-}" = "MINGW64" ]; then
            echo "Windows (MSYS2 MINGW64) host detected: building .exe."
            run_step ".exe" "$SCRIPT_DIR/build_windows.sh"
        else
            echo "Error: running under MSYS/MinGW, but not the MINGW64 environment (MSYSTEM='${MSYSTEM:-<unset>}')." >&2
            echo "Open 'MSYS2 MINGW64' from the Start Menu and re-run from there." >&2
            exit 1
        fi
        SKIPPED+=(".deb -- run build_deb.sh on a Linux machine")
        SKIPPED+=(".tar.gz -- run build_linux_portable.sh on a Linux machine")
        SKIPPED+=(".app -- run build_macos.sh on a macOS machine")
        ;;
    *)
        echo "Error: unrecognized platform '$(uname -s)'." >&2
        exit 1
        ;;
esac

echo
echo "== Summary =="
if [ "${#BUILT[@]}" -gt 0 ]; then
    printf 'Built:    %s\n' "${BUILT[@]}"
fi
if [ "${#SKIPPED[@]}" -gt 0 ]; then
    printf 'Skipped:  %s\n' "${SKIPPED[@]}"
fi
if [ "${#FAILED[@]}" -gt 0 ]; then
    printf 'FAILED:   %s\n' "${FAILED[@]}"
fi

if [ "${#SKIPPED[@]}" -gt 0 ]; then
    echo
    echo "To build all four archives from a single trigger instead of by hand"
    echo "on three separate machines, use the CI workflow:"
    echo "    gh workflow run release.yml"
    echo "(or trigger it from the Actions tab / by pushing a version tag)"
fi

[ "${#FAILED[@]}" -eq 0 ]
