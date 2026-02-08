# app/blueprints/absensi/tasks.py
# Mengalihkan ke modul sebenarnya di app/tasks/absensi_tasks.py

from __future__ import annotations

import importlib as _importlib

# Muat modul sumber yang asli
_src = _importlib.import_module("app.tasks.absensi_tasks")

# Ekspor semua simbol publik dari modul sumber
for _name in dir(_src):
    if not _name.startswith("_"):
        globals()[_name] = getattr(_src, _name)

# Definisikan __all__ agar linters & * import bekerja rapi
__all__ = [name for name in globals().keys() if not name.startswith("_")]
