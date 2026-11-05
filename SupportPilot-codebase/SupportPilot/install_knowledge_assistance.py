from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = Path.cwd()

required = [
    PROJECT / "app" / "main.py",
    PROJECT / "app" / "supportpilot" / "user_portal.py",
    PROJECT / "app" / "supportpilot" / "pipeline.py",
]
missing = [str(path) for path in required if not path.exists()]
if missing:
    raise SystemExit("Run this installer from the SupportPilot project root. Missing:\n" + "\n".join(missing))

main_path = PROJECT / "app" / "main.py"
main_text = main_path.read_text(encoding="utf-8")
anchor = "app.include_router(create_user_portal_router(pipeline))"
import_line = "from .supportpilot.knowledge_assistance_portal import create_knowledge_assistance_router"
route_line = "app.include_router(create_knowledge_assistance_router(pipeline))"

if anchor not in main_text:
    raise SystemExit(
        "Could not find the expected user-portal router registration in app/main.py. "
        "No files were changed. Add the knowledge router manually as described in README_KNOWLEDGE_ASSISTANCE.md."
    )
pipeline_source = (PROJECT / "app" / "supportpilot" / "pipeline.py").read_text(encoding="utf-8")
if "self.retriever" not in pipeline_source or "def resolve(" not in pipeline_source:
    raise SystemExit("Your pipeline does not expose the RAG retriever and resolve() workflow. Install and configure Milestone 2 first. No files were changed.")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = main_path.with_name(f"main.py.pre_knowledge_assistance_{stamp}.bak")
shutil.copy2(main_path, backup)

# Install the route module.
source_module = ROOT / "app" / "supportpilot" / "knowledge_assistance_portal.py"
target_module = PROJECT / "app" / "supportpilot" / "knowledge_assistance_portal.py"
if target_module.exists():
    shutil.copy2(target_module, target_module.with_suffix(f".py.pre_knowledge_assistance_{stamp}.bak"))
shutil.copy2(source_module, target_module)

if import_line not in main_text:
    # Keep imports grouped with the other supportpilot imports.
    import_anchor = "from .supportpilot.user_portal import create_user_portal_router, record_status_event"
    if import_anchor in main_text:
        main_text = main_text.replace(import_anchor, import_anchor + "\n" + import_line, 1)
    else:
        # Fallback: insert before the application instance.
        app_anchor = "app = FastAPI("
        if app_anchor not in main_text:
            shutil.copy2(backup, main_path)
            raise SystemExit("Could not locate a safe import insertion point; main.py restored from backup.")
        main_text = main_text.replace(app_anchor, import_line + "\n\n" + app_anchor, 1)
if route_line not in main_text:
    main_text = main_text.replace(anchor, anchor + "\napp.include_router(create_knowledge_assistance_router(pipeline))", 1)

main_path.write_text(main_text, encoding="utf-8")

# Install the three user-portal files while retaining backups.
for relative in [
    Path("frontend/user/index.html"),
    Path("frontend/user/style.css"),
    Path("frontend/user/script.js"),
]:
    source = ROOT / relative
    target = PROJECT / relative
    if not source.exists():
        raise SystemExit(f"Overlay is incomplete: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.copy2(target, target.with_name(target.name + f".pre_knowledge_assistance_{stamp}.bak"))
    shutil.copy2(source, target)

print("Knowledge Retrieval + AI Assistance installed.")
print(f"Backup of app/main.py: {backup.name}")
print("Updated only app/main.py, one new router module, and frontend/user/{index.html,style.css,script.js}.")
print("No classifier artifacts, training scripts, or existing database files were modified.")
