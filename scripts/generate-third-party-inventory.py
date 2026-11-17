"""Generate a deterministic runtime dependency/license inventory from the active environment."""

from __future__ import annotations

import re
import shutil
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

ROOT = Path(__file__).resolve().parent.parent
LICENSE_DIR = ROOT / "third_party_licenses"
INVENTORY_PATH = ROOT / "THIRD_PARTY_INVENTORY.md"
RUNTIME_ROOTS = ["numpy", "Pillow", "pyatv", "pystray", "SoundCard", "zeroconf"]
BUILD_COMPONENTS = ["PyInstaller"]
LICENSE_OVERRIDES = {
    "annotated-types": "MIT",
    "numpy": "BSD-3-Clause (see bundled notices)",
    "pyinstaller": "GPL-2.0-or-later with bootloader exception",
    "tinytag": "MIT",
}


def dependency_closure(names: list[str]) -> dict[str, object]:
    found: dict[str, object] = {}
    pending = list(names)
    while pending:
        name = pending.pop()
        key = canonicalize_name(name)
        if key in found:
            continue
        package = distribution(name)
        found[key] = package
        for raw_requirement in package.requires or []:
            requirement = Requirement(raw_requirement)
            if requirement.marker and not requirement.marker.evaluate():
                continue
            pending.append(requirement.name)
    return found


def license_label(metadata) -> str:
    package_key = canonicalize_name(metadata.get("Name", ""))
    if package_key in LICENSE_OVERRIDES:
        return LICENSE_OVERRIDES[package_key]
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    license_value = (metadata.get("License") or "").strip().splitlines()
    if license_value and len(license_value[0]) <= 100:
        return license_value[0]
    classifiers = [
        value.removeprefix("License :: ")
        for value in metadata.get_all("Classifier") or []
        if value.startswith("License :: ")
    ]
    return classifiers[-1] if classifiers else "See included license file"


def safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")


def copy_license_files(package, package_name: str, version: str) -> int:
    copied = 0
    package_dir = LICENSE_DIR / f"{safe_name(package_name)}-{safe_name(version)}"
    for relative in package.files or []:
        filename = Path(str(relative)).name.lower()
        if not any(marker in filename for marker in ("license", "copying", "notice")):
            continue
        source = Path(package.locate_file(relative))
        if not source.is_file():
            continue
        package_dir.mkdir(parents=True, exist_ok=True)
        destination = package_dir / safe_name(Path(str(relative)).name)
        if destination.exists():
            destination = package_dir / f"{copied}-{destination.name}"
        shutil.copy2(source, destination)
        copied += 1
    return copied


def main() -> None:
    packages = dependency_closure(RUNTIME_ROOTS)
    for name in BUILD_COMPONENTS:
        try:
            package = distribution(name)
        except PackageNotFoundError:
            continue
        packages[canonicalize_name(name)] = package

    if LICENSE_DIR.exists():
        shutil.rmtree(LICENSE_DIR)
    LICENSE_DIR.mkdir(parents=True)

    rows = []
    for key, package in sorted(packages.items()):
        metadata = package.metadata
        name = metadata.get("Name", key)
        version = package.version
        copied = copy_license_files(package, name, version)
        scope = "build" if canonicalize_name(name) in {canonicalize_name(item) for item in BUILD_COMPONENTS} else "runtime"
        rows.append(f"| {name} | {version} | {scope} | {license_label(metadata)} | {copied} |")

    content = "\n".join(
        [
            "# Third-Party Dependency Inventory",
            "",
            "Generated from the clean v1.0.0-beta.1 build environment. License metadata is informational; the exact distribution license files are under `third_party_licenses/`.",
            "",
            "| Package | Version | Scope | Declared license | License files |",
            "|---|---:|---|---|---:|",
            *rows,
            "",
        ]
    )
    INVENTORY_PATH.write_text(content, encoding="utf-8")


if __name__ == "__main__":
    main()
