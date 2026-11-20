"""Run E2E against disposable storage instead of the operator's CRM files."""
from pathlib import Path
import os
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
storage = Path(os.environ["PW_STORAGE_DIR"]).resolve()
if not storage.is_relative_to(ROOT / ".playwright"):
    raise RuntimeError("E2E storage must be inside .playwright")
storage.mkdir(parents=True, exist_ok=True)
os.environ["DATABASE_URL"] = "sqlite:///" + (storage / "test.sqlite3").as_posix()
os.environ["AUTO_ALEMBIC_ON_STARTUP"] = "0"
os.environ["RESET_DB_ON_START"] = "0"

from app import main

main.UPLOADS_DIR = storage / "uploads"
main.GENERATED_DIR = storage / "generated"
main.TEMPLATES_DIR = storage / "templates"
main.TEMPLATES_MANAGER_DIR = main.TEMPLATES_DIR / "manager_files"
main.UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
shutil.copytree(ROOT / "templates" / "Podacha", main.TEMPLATES_DIR / "Podacha", dirs_exist_ok=True)
for marker in (".document-intake-enabled", ".document-upload-enabled"):
    (main.UPLOADS_DIR / marker).touch()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(main.app, host="127.0.0.1", port=int(os.environ.get("PW_API_PORT", "18080")))
