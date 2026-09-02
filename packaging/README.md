# Packaging

Builds Simple Initiative Tracker into all four of its distribution
formats: a Debian package (`.deb`), a portable Linux bundle
(`.tar.gz`), a portable Windows build (`.exe`), and a macOS app
bundle (`.app`).

## Layout

```
packaging/
  common/
    app_metadata.sh     -- shared name/id constants, sourced by every script
    version.sh           -- reads $VERSION from pyproject.toml (single source of truth)
  debian/                -- control/postinst/desktop-entry/icon inputs for build_deb.sh
  linux/
    collect_shared_libs.py  -- ldd-based .so dependency closure walker
  windows/
    collect_dlls.py      -- objdump-based .dll dependency closure walker
    launcher.c            -- native launcher stub, compiled at build time
  macos/
    collect_dylibs.py    -- otool-based .dylib dependency closure walker + @rpath rewriting
    Info.plist.in         -- Info.plist template

  build_deb.sh            -- .deb          (Linux, run anywhere with dpkg-deb)
  build_linux_portable.sh -- .tar.gz       (Linux, run on the target arch)
  build_windows.sh        -- .exe          (Windows, MSYS2 MINGW64 shell only)
  build_macos.sh          -- .app          (macOS only)
  build_all.sh             -- runs whichever of the above are possible on this machine

  dist/    -- build output (gitignored)
  build/   -- build scratch space (gitignored)
```

## Quick start

```sh
./packaging/build_all.sh
```

This builds whatever your current machine can natively build, and
tells you plainly what it couldn't. **No single machine can build all
four** -- a real Windows `.exe` needs an actual Windows/MSYS2
toolchain, a real macOS `.app` needs actual macOS, and there's no
reliable way to cross-compile a GTK4 + GObject Introspection +
PyGObject application for a different OS than the one doing the
building. This isn't a shortcut particular to this project; it's why
GIMP, Inkscape, and every other cross-platform GTK app build their
releases on three separate machines (or CI runners), not one.

For all four archives from a single trigger, use the CI workflow
instead:

```sh
gh workflow run release.yml
```

(or trigger `.github/workflows/release.yml` from the Actions tab, or
by pushing a tag like `v1.0.0`). It builds each format on its own
native GitHub-hosted runner (`ubuntu-latest`, `windows-latest`,
`macos-latest`) and collects every artifact from the one run -- the
CI equivalent of running `build_all.sh` on three machines at once. A
tag push additionally publishes the four archives to a GitHub
Release.

## Running one format directly

Each script can also be run on its own, always from anywhere (they
resolve their own paths relative to the script's own location):

```sh
./packaging/build_deb.sh
./packaging/build_linux_portable.sh
./packaging/build_windows.sh   # from an MSYS2 MINGW64 shell
./packaging/build_macos.sh     # on macOS
```

Each prints its own prerequisites and exact output path when it runs
(and `build_deb.sh`, `build_linux_portable.sh` docstrings/comments
have the full detail on what gets bundled and why).

## Design notes

**Version is single-sourced.** Every script reads `$VERSION` from
`pyproject.toml` via `common/version.sh` -- nothing hand-maintains a
second copy that can drift (this replaced an earlier setup where
`debian/control`'s own `Version:` field had silently gone stale
against `pyproject.toml`).

**The two portable builds (Linux, and in spirit Windows/macOS too)
don't use PyInstaller.** They each walk the real shared-library
dependency graph from scratch (`ldd`/`objdump`/`otool` respectively)
with an explicit, documented denylist for what must come from the
host (glibc and the graphics/display stack on Linux; the core
Windows DLL family; macOS's own system frameworks) versus what
travels in the bundle (GTK4, GLib, Pango, cairo, HarfBuzz, gdk-pixbuf,
and their own dependencies). This is more transparent than a
PyInstaller onefile build and avoids PyInstaller's rougher handling of
GObject Introspection typelibs on Linux/macOS. Windows uses PyInstaller-adjacent
tooling only for the final single-.exe packaging step (7-Zip SFX), not
for dependency discovery.

**Verified for real, on this machine, where the tooling allows it:**
`build_deb.sh` and `build_linux_portable.sh` are both Linux-native and
were actually run end-to-end -- the `.deb` was installed with `dpkg
-i` and confirmed to launch; the portable `.tar.gz` was extracted to
an unrelated directory and run with `LD_LIBRARY_PATH`, `PYTHONPATH`,
`GI_TYPELIB_PATH`, and any venv entirely stripped from the
environment, confirming it doesn't quietly depend on anything from
the machine it was built on. `windows/launcher.c` was cross-compiled
with `mingw-w64-gcc` and confirmed to produce a valid PE32+
executable. `build_windows.sh`, `build_macos.sh`, and the CI
workflow's Windows/macOS jobs are believed correct from careful
review of the real toolchains involved, but haven't been run on
actual Windows or macOS hardware -- treat their first real run as the
final verification step, not this document.
