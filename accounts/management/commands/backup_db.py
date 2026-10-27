"""Backs up the MongoDB database into FS_BACKUP_DIR and keeps the newest FS_BACKUP_KEEP files.
    python manage.py backup_db
Atlas free clusters (M0) have no automatic backups, so run this every night (cron / Task Scheduler) and copy the
folder somewhere off the server.

If the `mongodump` tool is installed it is used (file ending .archive.gz). Otherwise a built-in exporter writes a
.jsonl.gz file (one line per document, in MongoDB Extended JSON). Restore either one with:
    python manage.py restore_db backups/<file>
"""
import gzip
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

from bson import json_util
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Dump the database to a backup file and delete old backups."

    def add_arguments(self, parser):
        parser.add_argument("--dir", help="Folder for the backup (default FS_BACKUP_DIR)")

    def handle(self, *args, **opts):
        db = settings.DATABASES["default"]
        folder = Path(opts["dir"] or settings.BACKUP_DIR)
        folder.mkdir(parents=True, exist_ok=True)
        stamp = f"{db['NAME']}-{datetime.now():%Y%m%d-%H%M%S}"
        if shutil.which("mongodump"):
            out = folder / f"{stamp}.archive.gz"
            res = subprocess.run(["mongodump", f"--uri={db['HOST']}", f"--db={db['NAME']}", f"--archive={out}", "--gzip"],
                                 capture_output=True, text=True)
            if res.returncode != 0:
                out.unlink(missing_ok=True)
                raise CommandError(f"mongodump failed: {res.stderr.strip()[:300]}")
        else:
            out = folder / f"{stamp}.jsonl.gz"
            mongo = connection.database
            try:
                with gzip.open(out, "wt", encoding="utf-8") as fh:
                    for name in sorted(mongo.list_collection_names()):
                        if name.startswith("system."):
                            continue
                        for doc in mongo[name].find():
                            fh.write(json_util.dumps({"c": name, "d": doc}) + "\n")
            except Exception as exc:                                                    # noqa: BLE001
                out.unlink(missing_ok=True)
                raise CommandError(f"Backup failed: {exc}")
        old = []
        for pattern in (f"{db['NAME']}-*.archive.gz", f"{db['NAME']}-*.jsonl.gz"):
            old += sorted(folder.glob(pattern), reverse=True)[settings.BACKUP_KEEP:]
        for f in old:
            f.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f"Backup written: {out} ({out.stat().st_size // 1024} KB); removed {len(old)} old file(s)."))
