"""Safely replace the legacy monolithic M3 module with modular packages.

Run from the existing SupportPilot project root. This migration keeps the existing
API routes and the compatibility import app.supportpilot.milestone3 unchanged.
"""
from __future__ import annotations
import compileall
import shutil
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path.cwd().resolve()
OVERLAY = Path(__file__).resolve().parent
STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
SOURCE_PACKAGE = OVERLAY / "app" / "supportpilot" / "m3"
TARGET_SUPPORTPILOT = PROJECT / "app" / "supportpilot"
TARGET_PACKAGE = TARGET_SUPPORTPILOT / "m3"
TARGET_SHIM = TARGET_SUPPORTPILOT / "milestone3.py"

required = [
    PROJECT / "app" / "main.py",
    PROJECT / "app" / "supportpilot" / "db.py",
    PROJECT / "app" / "supportpilot" / "pipeline.py",
]
missing = [str(path.relative_to(PROJECT)) for path in required if not path.is_file()]
if missing:
    raise SystemExit(
        "Run this installer from the existing SupportPilot project root. Missing:\n- "
        + "\n- ".join(missing)
    )
if not (SOURCE_PACKAGE / "__init__.py").is_file():
    raise SystemExit("Modular source package is incomplete: app/supportpilot/m3/__init__.py is missing.")

main_text = (PROJECT / "app" / "main.py").read_text(encoding="utf-8")
if "create_m3_router" not in main_text or "init_m3_schema" not in main_text:
    raise SystemExit(
        "Milestone 3 is not yet wired into app/main.py. Install the original M3 overlay first; "
        "this package only refactors its implementation into smaller modules."
    )

# Back up existing source before any mutation.
package_backup = TARGET_SUPPORTPILOT / f"m3.pre_modular_{STAMP}"
shim_backup = TARGET_SUPPORTPILOT / f"milestone3.py.pre_modular_{STAMP}.bak"
if TARGET_PACKAGE.exists():
    shutil.copytree(TARGET_PACKAGE, package_backup)
    print(f"Backup: {package_backup.relative_to(PROJECT)}")
if TARGET_SHIM.exists():
    shutil.copy2(TARGET_SHIM, shim_backup)
    print(f"Backup: {shim_backup.relative_to(PROJECT)}")

staging = TARGET_SUPPORTPILOT / f"m3.installing_{STAMP}"
try:
    shutil.copytree(SOURCE_PACKAGE, staging)
    if TARGET_PACKAGE.exists():
        shutil.rmtree(TARGET_PACKAGE)
    staging.replace(TARGET_PACKAGE)
    shutil.copy2(OVERLAY / "app" / "supportpilot" / "milestone3.py", TARGET_SHIM)

    ok = compileall.compile_dir(str(TARGET_PACKAGE), quiet=1, force=True)
    if not ok:
        raise RuntimeError("Python compilation failed for the installed M3 package.")

    # Validate the main app still imports through the compatibility shim.
    installed_main = (PROJECT / "app" / "main.py").read_text(encoding="utf-8")
    if ".supportpilot.milestone3 import" not in installed_main and ".supportpilot.m3 import" not in installed_main:
        raise RuntimeError("app/main.py does not import the M3 lifecycle/router functions.")

except Exception as exc:
    if TARGET_PACKAGE.exists():
        shutil.rmtree(TARGET_PACKAGE)
    if package_backup.exists():
        shutil.copytree(package_backup, TARGET_PACKAGE)
    if shim_backup.exists():
        shutil.copy2(shim_backup, TARGET_SHIM)
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    raise SystemExit(f"Modular M3 installation failed and prior files were restored: {exc}") from exc

print("\nModular Milestone 3 installed successfully.")
print("The existing /m3 API paths remain unchanged; existing frontend/admin/m3.js remains compatible.")
print("No classifier artifacts, training scripts, datasets, Chroma index or ticket rows were modified.")
print("Next: restart Uvicorn and verify GET /m3/status with X-SupportPilot-Admin-Key.")
