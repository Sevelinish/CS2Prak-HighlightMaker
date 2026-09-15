from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
RELEASE_NAME = "HighlighterCS2"
RELEASE_DIRECTORY = DIST / RELEASE_NAME
STAGING_DIRECTORY = DIST / f".{RELEASE_NAME}-staging"
EXECUTABLE_NAME = f"{RELEASE_NAME}.exe"
BUNDLE_DIRECTORY = "_internal"
SHIPPED_FILES = ("README.md", "README.ru.md")
CONFIG_FILE = "config.json"
CONFIG_TEMPLATE = "config.example.json"
SHIPPED_DIRECTORIES = ("demos",)
COPIED_DIRECTORIES = ("docs",)
BUNDLED_PACKAGES = ("demoparser2", "polars", "pyarrow", "numpy", "pandas", "tqdm", "rich")
BUNDLED_PACKAGE_ARGUMENTS = tuple(
    argument for package in BUNDLED_PACKAGES for argument in ("--collect-all", package)
)


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
        "--distpath",
        str(STAGING_DIRECTORY),
        *BUNDLED_PACKAGE_ARGUMENTS,
        str(ROOT / "main.py"),
    ]
    try:
        subprocess.run(arguments, check=True, cwd=str(ROOT))
    except subprocess.CalledProcessError as error:
        raise SystemExit(f"PyInstaller failed (exit {error.returncode}).") from error


def install_release() -> None:
    staged = STAGING_DIRECTORY / RELEASE_NAME
    if not staged.is_dir():
        raise SystemExit(f"PyInstaller produced nothing at {staged}")

    RELEASE_DIRECTORY.mkdir(parents=True, exist_ok=True)
    remove_previous_build()

    for item in staged.iterdir():
        destination = RELEASE_DIRECTORY / item.name
        if item.is_dir():
            shutil.copytree(item, destination, dirs_exist_ok=True)
        else:
            shutil.copy2(item, destination)


def remove_previous_build() -> None:
    bundle = RELEASE_DIRECTORY / BUNDLE_DIRECTORY
    executable = RELEASE_DIRECTORY / EXECUTABLE_NAME

    if bundle.is_dir():
        shutil.rmtree(bundle, ignore_errors=True)

    if not executable.is_file():
        return
    try:
        executable.unlink()
    except OSError as error:
        raise SystemExit(
            f"{EXECUTABLE_NAME} is in use and cannot be replaced ({error.strerror}). "
            f"Close it and build again."
        ) from error


def copy_release_files() -> None:
    for file_name in SHIPPED_FILES:
        source = ROOT / file_name
        if source.is_file():
            shutil.copy2(source, RELEASE_DIRECTORY / file_name)

    copy_default_config()

    for directory_name in SHIPPED_DIRECTORIES:
        (RELEASE_DIRECTORY / directory_name).mkdir(parents=True, exist_ok=True)

    for directory_name in COPIED_DIRECTORIES:
        source = ROOT / directory_name
        if source.is_dir():
            shutil.copytree(source, RELEASE_DIRECTORY / directory_name, dirs_exist_ok=True)


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
    shutil.rmtree(STAGING_DIRECTORY, ignore_errors=True)
    for spec in ROOT.glob("*.spec"):
        spec.unlink(missing_ok=True)


def main() -> int:
    run_pyinstaller()
    install_release()
    copy_release_files()
    clean()
    print(f"\nRelease ready: {RELEASE_DIRECTORY}")
    print("Your demos, clips, tools, logs and config.json were left untouched.")
    print(f"Run it with: {RELEASE_DIRECTORY / EXECUTABLE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
