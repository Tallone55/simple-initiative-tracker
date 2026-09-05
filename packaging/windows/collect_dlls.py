#!/usr/bin/env python3
"""Windows counterpart to linux/collect_shared_libs.py: resolves the
full DLL dependency closure for one or more seed DLLs/executables and
copies every resolved DLL into an output directory.

Meant to run under an MSYS2 MINGW64 shell, using `objdump` to read
each PE file's import table, then resolving each imported DLL name
against the Windows loader's own search order.

A denylist excludes DLLs the host Windows install must supply
instead of the bundle (kernel32, ntdll, user32, the api-ms-win-*
virtual DLLs, etc.).

Usage:
    collect_dlls.py --out DIR --search-path DIR [--search-path DIR ...] SEED [SEED ...]
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
    r"^bcryptprimitives\.dll$",
    r"^ncrypt\.dll$",
    r"^normaliz\.dll$",
    r"^wtsapi32\.dll$",
    r"^d3d\d*\.dll$",
    r"^dxgi\.dll$",
    r"^dcomp\.dll$",
    r"^usp10\.dll$",
    r"^dwrite\.dll$",
    r"^wldap32\.dll$",
    r"^hid\.dll$",
    r"^shcore\.dll$",
    r"^cfgmgr32\.dll$",
    r"^api-ms-win-.*\.dll$",
    r"^ext-ms-win-.*\.dll$",
    r"^msvcrt\.dll$",
    r"^ucrtbase\.dll$",
    r"^vcruntime\d*\.dll$",
]
_DENYLIST_RE = re.compile("(" + "|".join(_DENYLIST_PATTERNS) + ")", re.IGNORECASE)

_IMPORT_LINE_RE = re.compile(r"^\s*DLL Name:\s*(\S+)\s*$", re.IGNORECASE | re.MULTILINE)


def _imported_dll_names(path):
    result = subprocess.run(["objdump", "-p", str(path)], capture_output=True, text=True)
    return set(_IMPORT_LINE_RE.findall(result.stdout))


def _resolve(name, search_paths):
    """The first existing DLL named `name` (case-insensitive) across
    `search_paths`, in order."""
    for directory in search_paths:
        for candidate in Path(directory).glob("*"):
            if candidate.is_file() and candidate.name.lower() == name.lower():
                return candidate
    return None


def collect_closure(seeds, search_paths, walk_only_seeds=()):
    """Returns {dll_name: resolved_path}, denylisted/unresolvable
    entries excluded. Includes `seeds` themselves, not just their
    imported DLL names: a seed only ends up copied into the bundle
    today if something else in the seed set happens to import it
    directly, so anything seeded specifically because nothing else in
    the set imports it would otherwise be silently missing from the
    output (found and fixed for exactly this reason in the macOS
    collector's own librsvg seed; the same design gap exists here).
    `walk_only_seeds` are walked for their own imports the same way,
    but never added to the output themselves -- for a seed that's
    only here to make sure its *imports* get discovered, because the
    seed file itself is already being copied to some other, more
    specific destination by the caller. If a walk-only seed also
    turns out to be some other file's regular import, it's still
    collected normally through that path -- this only suppresses
    adding the seed *as a seed*."""
    closure = {}
    walk_only_paths = {Path(s).resolve() for s in walk_only_seeds}
    queue = list(seeds) + list(walk_only_seeds)
    seen = set()

    while queue:
        current = queue.pop()
        current_path = Path(current).resolve()
        if current_path in seen or not current_path.is_file():
            continue
        seen.add(current_path)
        seed_name = Path(current).name
        if seed_name not in closure and current_path not in walk_only_paths:
            closure[seed_name] = current_path

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
    parser.add_argument(
        "--walk-only", action="append", default=[], dest="walk_only",
        help="Seed to walk for imports without copying the seed itself (repeatable) -- "
             "for a seed already copied to its own destination by the caller",
    )
    parser.add_argument("seeds", nargs="+", help="Seed DLLs/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds, args.search_paths, args.walk_only)

    for name, resolved in sorted(closure.items()):
        shutil.copy2(resolved, out_dir / name)

    print(f"Collected {len(closure)} DLLs into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
