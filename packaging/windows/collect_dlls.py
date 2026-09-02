#!/usr/bin/env python3
"""Windows counterpart to linux/collect_shared_libs.py: resolves the
full DLL dependency closure for one or more seed DLLs/executables and
copies every resolved DLL into an output directory, so the portable
Windows build is self-contained the same way the Linux portable
bundle and the macOS .app bundle are -- GTK4, GLib, Pango, cairo,
HarfBuzz, gdk-pixbuf, and their MSYS2-provided dependencies all travel
with the app.

Meant to run under an MSYS2 MINGW64 shell, using `objdump` (part of
MSYS2's binutils, always present alongside a mingw-w64 toolchain) to
read each PE file's import table, then resolving each imported DLL
name against the same search path order the Windows loader itself
uses (application directory first, then the provided search
directories -- MSYS2's mingw64/bin here).

A denylist excludes DLLs the *host* Windows install must supply
instead of the bundle -- the core OS/CRT DLL family (kernel32,
ntdll, user32, gdi32, the api-ms-win-* virtual DLLs, ...) -- since
these are versioned and serviced by Windows itself; bundling a
possibly-mismatched copy is far more likely to break things than
help, the same reasoning collect_shared_libs.py applies to glibc on
Linux.

Usage:
    collect_dlls.py --out DIR --search-path DIR [--search-path DIR ...] SEED [SEED ...]

Each SEED is a path to a DLL or executable to start from.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

_DENYLIST_PATTERNS = [
    r"^kernel32\.dll$",
    r"^ntdll\.dll$",
    r"^user32\.dll$",
    r"^gdi32\.dll$",
    r"^gdiplus\.dll$",
    r"^advapi32\.dll$",
    r"^shell32\.dll$",
    r"^shlwapi\.dll$",
    r"^ole32\.dll$",
    r"^oleaut32\.dll$",
    r"^comdlg32\.dll$",
    r"^comctl32\.dll$",
    r"^winmm\.dll$",
    r"^winspool\.drv$",
    r"^ws2_32\.dll$",
    r"^wsock32\.dll$",
    r"^imm32\.dll$",
    r"^msimg32\.dll$",
    r"^opengl32\.dll$",
    r"^glu32\.dll$",
    r"^version\.dll$",
    r"^setupapi\.dll$",
    r"^rpcrt4\.dll$",
    r"^crypt32\.dll$",
    r"^secur32\.dll$",
    r"^dnsapi\.dll$",
    r"^iphlpapi\.dll$",
    r"^netapi32\.dll$",
    r"^userenv\.dll$",
    r"^psapi\.dll$",
    r"^dwmapi\.dll$",
    r"^uxtheme\.dll$",
    r"^bcrypt\.dll$",
    r"^ncrypt\.dll$",
    r"^normaliz\.dll$",
    r"^wtsapi32\.dll$",
    r"^d3d\d*\.dll$",
    r"^dxgi\.dll$",
    r"^api-ms-win-.*\.dll$",
    r"^ext-ms-win-.*\.dll$",
    r"^msvcrt\.dll$",
    r"^ucrtbase\.dll$",
    r"^vcruntime\d*\.dll$",
]
_DENYLIST_RE = re.compile("(" + "|".join(_DENYLIST_PATTERNS) + ")", re.IGNORECASE)

_IMPORT_LINE_RE = re.compile(r"^\s*DLL Name:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)


def _imported_dll_names(path):
    """Direct DLL imports of `path`, read from `objdump -p`'s "DLL
    Name:" lines -- one per imported DLL, however many symbols are
    actually pulled from it."""
    result = subprocess.run(["objdump", "-p", str(path)], capture_output=True, text=True)
    return set(_IMPORT_LINE_RE.findall(result.stdout))


def _resolve(name, search_paths):
    """The first existing DLL named `name` (case-insensitively, as
    Windows itself treats filenames) across `search_paths`, in order
    -- mirrors the Windows loader's own search order for a bundle
    that has no DLLs of its own alongside the executable yet."""
    for directory in search_paths:
        for candidate in Path(directory).glob("*"):
            if candidate.is_file() and candidate.name.lower() == name.lower():
                return candidate
    return None


def collect_closure(seeds, search_paths):
    """Recursively resolves every seed's full DLL import closure.
    Returns {dll_name: resolved_path}, denylisted and unresolvable
    (host-supplied, or simply not found) entries excluded."""
    closure = {}
    queue = list(seeds)
    seen = set()

    while queue:
        current = queue.pop()
        current_path = Path(current).resolve()
        if current_path in seen or not current_path.is_file():
            continue
        seen.add(current_path)

        for name in _imported_dll_names(current_path):
            if _DENYLIST_RE.match(name):
                continue
            if name in closure:
                continue
            resolved = _resolve(name, search_paths)
            if resolved is None:
                print(f"warning: could not resolve {name} (imported by {current_path.name})", file=sys.stderr)
                continue
            closure[name] = resolved
            queue.append(resolved)

    return closure


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output directory for resolved DLLs")
    parser.add_argument(
        "--search-path", action="append", required=True, dest="search_paths",
        help="Directory to resolve imported DLL names against (repeatable, tried in order)",
    )
    parser.add_argument("seeds", nargs="+", help="Seed DLLs/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds, args.search_paths)

    for name, resolved in sorted(closure.items()):
        shutil.copy2(resolved, out_dir / name)

    print(f"Collected {len(closure)} DLLs into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
