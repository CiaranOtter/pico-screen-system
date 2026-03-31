#!/usr/bin/env python3
"""
upload.py — Upload project to Pico W via mpremote, respecting an ignore file.

Usage:
  python upload.py [--ignore FILE] [--port PORT] [--dry-run]

Examples:
  python upload.py
  python upload.py --ignore .micropicoignore
  python upload.py --port /dev/ttyACM0
  python upload.py --dry-run
"""

import argparse
import fnmatch
import os
import subprocess
import sys
from pathlib import Path


# ── Ignore parsing ────────────────────────────────────────────────────────────

def load_patterns(path: str) -> list[str]:
    """Load non-comment, non-empty lines from an ignore file."""
    try:
        with open(path) as f:
            return [
                line.strip() for line in f
                if line.strip() and not line.strip().startswith('#')
            ]
    except FileNotFoundError:
        print(f"Warning: ignore file '{path}' not found — uploading everything")
        return []


def is_ignored(rel: Path, patterns: list[str]) -> bool:
    """
    Return True if rel matches any ignore pattern.

    Supports:
      - Simple name globs:   *.pyc, *.pyo
      - Directory patterns:  __pycache__/  (trailing slash means dir-only)
      - Path patterns:       lib/gc9a01py/
      - Double-star prefix:  **/__pycache__/
    """
    posix = rel.as_posix()   # e.g. "lib/gc9a01py/fonts"
    name  = rel.name         # e.g. "fonts"

    for raw in patterns:
        p            = raw.rstrip('/')
        is_dir_pat   = raw.endswith('/')

        if not p:
            continue

        # ** prefix — match name or any path component
        if p.startswith('**/'):
            tail = p[3:]
            if fnmatch.fnmatch(name, tail):
                return True
            if fnmatch.fnmatch(posix, tail):
                return True
            for part in rel.parts:
                if fnmatch.fnmatch(part, tail):
                    return True
            continue

        # Pattern contains '/' — match against full relative path
        if '/' in p:
            if posix == p:
                return True
            if posix.startswith(p + '/'):
                return True
            if fnmatch.fnmatch(posix, p):
                return True
            continue

        # Plain name glob — match against just the file/dir name
        if fnmatch.fnmatch(name, p):
            return True

    return False


# ── mpremote helpers ──────────────────────────────────────────────────────────

def mpremote_cmd(port: str | None) -> list[str]:
    base = ['mpremote']
    if port:
        base += ['connect', port]
    return base


def run(cmd: list[str], dry_run: bool) -> None:
    print('  ' + ' '.join(cmd))
    if not dry_run:
        result = subprocess.run(cmd)
        if result.returncode != 0:
            # Non-fatal — e.g. mkdir on existing directory
            print(f"  ↳ exited {result.returncode}", file=sys.stderr)


def remote_mkdir(base: list[str], path: Path, dry_run: bool) -> None:
    """Create a directory on the Pico, ignoring 'already exists' errors."""
    cmd = base + ['exec', f'import os\ntry:\n os.mkdir("/{path.as_posix()}")\nexcept OSError:\n pass']
    run(cmd, dry_run)


def remote_cp(base: list[str], local: Path, dry_run: bool) -> None:
    run(base + ['cp', str(local), f':{local.as_posix()}'], dry_run)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description='Upload project to Pico W via mpremote'
    )
    ap.add_argument('--ignore', '-i', default='.micropicoignore', metavar='FILE',
                    help='Ignore file  (default: .micropicoignore)')
    ap.add_argument('--port', '-p', default=None, metavar='PORT',
                    help='Serial port  (default: auto-detect)')
    ap.add_argument('--dry-run', '-n', action='store_true',
                    help='Print commands without executing them')
    args = ap.parse_args()

    root     = Path('.')
    patterns = load_patterns(args.ignore)
    base     = mpremote_cmd(args.port)

    # ── Walk project tree ────────────────────────────────────────────────────
    dirs_to_create: list[Path] = []
    files_to_copy:  list[Path] = []

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        rel_dir = Path(dirpath).relative_to(root)

        # If this directory itself is ignored, skip it entirely
        if rel_dir != Path('.') and is_ignored(rel_dir, patterns):
            dirnames.clear()
            continue

        # Prune subdirectories that are ignored (prevents descending into them)
        dirnames[:] = sorted(
            d for d in dirnames
            if not is_ignored(rel_dir / d, patterns)
        )

        if rel_dir != Path('.'):
            dirs_to_create.append(rel_dir)

        for fname in sorted(filenames):
            rel_file = rel_dir / fname if rel_dir != Path('.') else Path(fname)
            if not is_ignored(rel_file, patterns):
                files_to_copy.append(rel_file)

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"Ignore file : {args.ignore}  ({len(patterns)} patterns)")
    print(f"Directories : {len(dirs_to_create)}")
    print(f"Files       : {len(files_to_copy)}")
    if args.dry_run:
        print("(dry run — no commands will be executed)\n")
    else:
        print()

    # ── 1. Create remote directories ─────────────────────────────────────────
    if dirs_to_create:
        print("── Creating directories ──")
        for d in dirs_to_create:
            remote_mkdir(base, d, args.dry_run)

    # ── 2. Copy files ─────────────────────────────────────────────────────────
    if files_to_copy:
        print("\n── Copying files ──")
        for i, f in enumerate(files_to_copy, 1):
            print(f"  [{i}/{len(files_to_copy)}] {f}")
            if not args.dry_run:
                result = subprocess.run(base + ['cp', str(f), f':{f.as_posix()}'])
                if result.returncode != 0:
                    print(f"  ↳ FAILED (exit {result.returncode})", file=sys.stderr)

    print(f"\n✓ Done — {len(files_to_copy)} files uploaded")


if __name__ == '__main__':
    main()
