#!/usr/bin/env python3
"""macOS counterpart to linux/collect_shared_libs.py and windows/
collect_dlls.py: resolves the full dylib dependency closure for one
or more seed dylibs/executables, via recursive `otool -L`, copies
every resolved dylib into an output directory, and -- unlike the
Linux/Windows collectors, which rely on LD_LIBRARY_PATH/same-directory
search at runtime -- rewrites each dylib's own install name and every
reference to it from other collected dylibs (via `install_name_tool`)
to `@rpath/<name>`, the standard way a relocatable macOS .app bundle
is actually built (the same approach tools like dylibbundler and
macdeployqt take). build_macos.sh sets an @executable_path-relative
rpath on the bundle's own Python interpreter so those @rpath
references resolve to Contents/Frameworks at runtime.

A denylist excludes dylibs the *host* macOS must supply instead of
the bundle: the system framework family (Cocoa, CoreFoundation,
AppKit, ...) and libSystem itself, which are versioned and serviced
by macOS -- bundling a possibly-mismatched copy is far more likely to
break things than help, the same reasoning collect_shared_libs.py
applies to glibc on Linux and collect_dlls.py applies to the core
Windows DLL family.

Usage:
    collect_dylibs.py --out DIR SEED [SEED ...]

Each SEED is a path to a dylib or executable to start from.
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

_DENYLIST_PATTERNS = [
    # Everything under /usr/lib is core-OS-provided on macOS -- a
    # blanket prefix match, not an attempt to enumerate individual
    # library name patterns: a previous, narrower pattern here
    # (matching only unversioned names like "libfoo.dylib") missed
    # every *versioned* one, e.g. "libiconv.2.dylib" or
    # "libbz2.1.0.dylib" -- version segments contain a "." the
    # character class didn't allow -- and those are the overwhelming
    # majority of real /usr/lib dependency names in practice. Modern
    # macOS (Big Sur+) doesn't even keep most of these as real files
    # on disk any more (only inside the single "dyld shared cache"),
    # so a missed match here doesn't just wrongly attempt to bundle a
    # system library -- it fails to find the file at all and prints a
    # spurious "could not resolve" warning for something completely
    # normal and expected.
    r"^/usr/lib/",
    r"^/System/Library/Frameworks/",
    r"^/System/Library/PrivateFrameworks/",
]
_DENYLIST_RE = re.compile("(" + "|".join(_DENYLIST_PATTERNS) + ")")

# otool -L output lines look like:
#     /opt/homebrew/opt/gtk4/lib/libgtk-4.1.dylib (compatibility version 1.0.0, current version 1.0.0)
_OTOOL_LINE_RE = re.compile(r"^\s*(\S+)\s+\(compatibility version")

# otool -l's "cmd LC_RPATH" segments look like:
#     cmd LC_RPATH
#     ...
#         path /opt/homebrew/opt/librsvg/lib (offset 12)
_LC_RPATH_RE = re.compile(r"^\s*path\s+(\S+)\s+\(offset", re.MULTILINE)


def _dependencies(path):
    """Direct dylib dependencies of `path` (as absolute paths, or
    @rpath/@loader_path-relative ones left as-is -- see _resolve),
    excluding the entry that's the file's own install name (the
    first line of otool -L's output, always self-referential)."""
    result = subprocess.run(["otool", "-L", str(path)], capture_output=True, text=True)
    lines = result.stdout.splitlines()[1:]  # first line is just "path:"
    deps = []
    for i, line in enumerate(lines):
        match = _OTOOL_LINE_RE.match(line)
        if not match:
            continue
        if i == 0:
            # A dylib's own first dependency line is its own install
            # name (id), not a real dependency, when built as a
            # shared library (skip); executables have no such line.
            id_result = subprocess.run(["otool", "-D", str(path)], capture_output=True, text=True)
            id_lines = [l for l in id_result.stdout.splitlines() if l.strip() and not l.endswith(":")]
            if id_lines and id_lines[0].strip() == match.group(1):
                continue
        deps.append(match.group(1))
    return deps


def _own_rpaths(path):
    """The LC_RPATH search-path entries actually embedded in `path`'s
    own Mach-O load commands (via `otool -l`) -- what @rpath/ actually
    means for this specific file, at the linker's own word for it,
    rather than assumed. A Homebrew-built dylib commonly references a
    sibling formula's own lib/ directory this way (e.g. gdk-pixbuf's
    SVG loader plugin depends on @rpath/librsvg-2.2.dylib, with an
    LC_RPATH pointing at librsvg's own opt/ prefix, not gdk-pixbuf's) --
    resolving @rpath/ against only the depending file's own directory,
    as an earlier version of this function did, misses exactly that
    case and silently ships an app with a broken SVG loader plugin."""
    result = subprocess.run(["otool", "-l", str(path)], capture_output=True, text=True)
    return [Path(m.group(1)) for m in _LC_RPATH_RE.finditer(result.stdout)]


def _resolve(name, loader_path, rpaths):
    """An @rpath/@loader_path/@executable_path-relative dependency
    name resolved against the resolving binary's own directory and
    its own real LC_RPATH entries (whichever actually contains the
    file) -- absolute paths pass through unchanged."""
    if name.startswith(("@rpath/", "@loader_path/", "@executable_path/")):
        basename = name.split("/")[-1]
        for directory in [loader_path, *rpaths]:
            candidate = directory / basename
            if candidate.is_file():
                return candidate
        return None
    return Path(name)


def collect_closure(seeds):
    """Recursively resolves every seed's full dylib dependency
    closure. Returns {resolved_path: original_dependency_name},
    denylisted entries excluded."""
    closure = {}
    queue = [Path(s).resolve() for s in seeds]
    seen = set()

    while queue:
        current = queue.pop()
        if current in seen or not current.is_file():
            continue
        seen.add(current)

        rpaths = _own_rpaths(current)
        for name in _dependencies(current):
            if _DENYLIST_RE.match(name):
                continue
            resolved = _resolve(name, current.parent, rpaths)
            if resolved is None or not resolved.is_file():
                print(f"warning: could not resolve {name} (depended on by {current.name})", file=sys.stderr)
                continue
            resolved = resolved.resolve()
            if resolved not in closure:
                closure[resolved] = name
            queue.append(resolved)

    return closure


def _rewrite_install_names(out_dir, collected_names):
    """Rewrites each collected dylib's own install name to
    @rpath/<name>, then rewrites every *other* collected dylib's
    reference to it the same way -- so the whole set only ever
    references itself relative to @rpath, matching the rpath
    build_macos.sh sets on the bundle's own Python interpreter."""
    dylib_paths = sorted(out_dir.glob("*.dylib"))
    for dylib in dylib_paths:
        subprocess.run(["install_name_tool", "-id", f"@rpath/{dylib.name}", str(dylib)], check=True)

    for dylib in dylib_paths:
        for name in collected_names:
            basename = Path(name).name
            if name.startswith("@") or "/" not in name:
                old_ref = name
            else:
                old_ref = name  # absolute path as originally referenced
            subprocess.run(
                ["install_name_tool", "-change", old_ref, f"@rpath/{basename}", str(dylib)],
                capture_output=True,  # a given dylib often doesn't reference every other one; errors expected
            )

    # install_name_tool invalidates whatever ad-hoc signature Homebrew
    # originally applied (required for arm64 dylibs to load at all) --
    # re-signed here with a fresh ad-hoc signature (still no real
    # certificate involved, just "-", the same thing Homebrew itself
    # used) rather than left in an invalidated state, matching what
    # dylibbundler/macdeployqt-style bundlers do after the same kind
    # of rewrite.
    for dylib in dylib_paths:
        subprocess.run(["codesign", "--force", "--sign", "-", str(dylib)], capture_output=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="Output directory for resolved dylibs")
    parser.add_argument("seeds", nargs="+", help="Seed dylibs/executables to resolve from")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    closure = collect_closure(args.seeds)

    for resolved, original_name in closure.items():
        dest = out_dir / resolved.name
        shutil.copy2(resolved, dest, follow_symlinks=True)
        dest.chmod(0o755)

    _rewrite_install_names(out_dir, list(closure.values()))

    print(f"Collected {len(closure)} dylibs into {out_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
