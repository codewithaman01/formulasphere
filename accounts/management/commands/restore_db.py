"""Restores a backup made by backup_db.   python manage.py restore_db backups/<file>  [--replace]
Without --replace, documents that already exist (same _id) are left alone and only missing ones are added."""
import gzip
import shutil
import subprocess
from pathlib import Path

from bson import json_util
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from pymongo import ReplaceOne
from pymongo.errors import BulkWriteError


class Command(BaseCommand):
    help = "Restore a backup file written by backup_db."

    def add_arguments(self, parser):
        parser.add_argument("file")
        parser.add_argument("--replace", action="store_true", help="Overwrite documents that already exist")

    def handle(self, *args, **o):
        path = Path(o["file"])
        if not path.exists():
            raise CommandError(f"{path} does not exist.")
        db = settings.DATABASES["default"]
        if path.name.endswith(".archive.gz"):
            if not shutil.which("mongorestore"):
                raise CommandError("mongorestore was not found. Install the MongoDB Database Tools.")
            cmd = ["mongorestore", f"--uri={db['HOST']}", f"--archive={path}", "--gzip", f"--nsInclude={db['NAME']}.*"]
            if o["replace"]:
                cmd.append("--drop")
            res = subprocess.run(cmd, capture_output=True, text=True)
            if res.returncode != 0:
                raise CommandError(f"mongorestore failed: {res.stderr.strip()[:300]}")
            self.stdout.write(self.style.SUCCESS("Restored."))
            return
        mongo = connection.database
        batches, counts = {}, {}

        def flush(name):
            ops = batches.pop(name, [])
            if not ops:
                return
            try:
                mongo[name].bulk_write(ops, ordered=False)
            except BulkWriteError as exc:
                if not all(e.get("code") == 11000 for e in exc.details.get("writeErrors", [])):
                    raise

        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                row = json_util.loads(line)
                name, doc = row["c"], row["d"]
                if o["replace"]:
                    batches.setdefault(name, []).append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
                else:
                    from pymongo import InsertOne
                    batches.setdefault(name, []).append(InsertOne(doc))
                counts[name] = counts.get(name, 0) + 1
                if len(batches[name]) >= 500:
                    flush(name)
        for name in list(batches):
            flush(name)
        self.stdout.write(self.style.SUCCESS("Restored: " + ", ".join(f"{k} ({v})" for k, v in sorted(counts.items()))))
