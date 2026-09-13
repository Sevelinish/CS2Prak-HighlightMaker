from __future__ import annotations

import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
RELEASE_NAME = "HighlighterCS2"
RELEASE_DIRECTORY = DIST / RELEASE_NAME
STAGING_DIRECTORY = DIST / f".{RELEASE_NAME}-keep"
SHIPPED_FILES = ("README.md",)
CONFIG_FILE = "config.json"
CONFIG_TEMPLATE = "config.example.json"
SHIPPED_DIRECTORIES = ("demos",)
PRESERVED_DIRECTORIES = ("tools", "work", "logs", "Highlighter", "demos")
PRESERVED_FILES = (CONFIG_FILE,)
BUNDLED_PACKAGES = ("demoparser2", "polars", "pyarrow", "numpy", "pandas", "tqdm", "rich")
BUNDLED_PACKAGE_ARGUMENTS = tuple(
    argument for package in BUNDLED_PACKAGES for argument in ("--collect-all", package)
)


@contextmanager
def preserved_runtime_data():
    if not RELEASE_DIRECTORY.is_dir():
        yield
        return

    shutil.rmtree(STAGING_DIRECTORY, ignore_errors=True)
    STAGING_DIRECTORY.mkdir(parents=True, exist_ok=True)
    rescued: list[str] = []

    try:
        locked: list[str] = []
        for name in PRESERVED_DIRECTORIES:
            source = RELEASE_DIRECTORY / name
            if not source.is_dir():
                continue
            try:
                source.rename(STAGING_DIRECTORY / name)
            except OSError:
                locked.append(name)
                continue
            rescued.append(name)

        for name in PRESERVED_FILES:
            source = RELEASE_DIRECTORY / name
            if not source.is_file():
                continue
            try:
                source.rename(STAGING_DIRECTORY / name)
            except OSError:
                locked.append(name)
                continue
            rescued.append(name)

        if rescued:
            print(f"Preserving across rebuild: {', '.join(rescued)}")
        if locked:
            print(
                f"In use, left in place (close anything holding them): {', '.join(locked)}"
            )

        yield
    finally:
        RELEASE_DIRECTORY.mkdir(parents=True, exist_ok=True)
        for name in rescued:
            destination = RELEASE_DIRECTORY / name
            if destination.is_dir():
                shutil.rmtree(destination, ignore_errors=True)
            else:
                destination.unlink(missing_ok=True)
            try:
                (STAGING_DIRECTORY / name).rename(destination)
            except OSError:
                shutil.copy2(STAGING_DIRECTORY / name, destination)
        shutil.rmtree(STAGING_DIRECTORY, ignore_errors=True)


def run_pyinstaller() -> None:
    arguments = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--console",
        "--name",
        RELEASE_NAME,
        "--paths",
        str(ROOT / "src"),
        *BUNDLED_PACKAGE_ARGUMENTS,
        str(ROOT / "main.py"),
    ]
    try:
        subprocess.run(arguments, check=True, cwd=str(ROOT))
    except subprocess.CalledProcessError as error:
        raise SystemExit(
            f"PyInstaller failed (exit {error.returncode}). "
            f"Close {RELEASE_NAME}.exe if it is still running and try again."
        ) from error


def copy_release_files() -> None:
    for file_name in SHIPPED_FILES:
        source = ROOT / file_name
        if source.is_file():
            shutil.copy2(source, RELEASE_DIRECTORY / file_name)

    copy_default_config()

    for directory_name in SHIPPED_DIRECTORIES:
        (RELEASE_DIRECTORY / directory_name).mkdir(parents=True, exist_ok=True)


def copy_default_config() -> None:
    destination = RELEASE_DIRECTORY / CONFIG_FILE
    if destination.is_file():
        return

    for candidate in (ROOT / CONFIG_FILE, ROOT / CONFIG_TEMPLATE):
        if candidate.is_file():
            shutil.copy2(candidate, destination)
            return


def clean() -> None:
    shutil.rmtree(BUILD, ignore_errors=True)
    for spec in ROOT.glob("*.spec"):
        spec.unlink(missing_ok=True)


def main() -> int:
    with preserved_runtime_data():
        run_pyinstaller()

    copy_release_files()
    clean()
    print(f"\nRelease ready: {RELEASE_DIRECTORY}")
    print(f"Run it with: {RELEASE_DIRECTORY / (RELEASE_NAME + '.exe')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
