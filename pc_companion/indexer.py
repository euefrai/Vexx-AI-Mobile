"""Disk-backed filename FTS index. No file contents, junction traversal or per-query scan."""
import os
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

EXCLUDED = {'$recycle.bin', 'system volume information', 'windows', 'node_modules',
            '.git', '.venv', '__pycache__', '.cache', 'appdata', 'programdata'}


class FileIndex:
    def __init__(self, path, roots):
        self.path, self.roots = Path(path), [Path(p).resolve() for p in roots]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.paused = threading.Event()
        self.running, self.error, self.count, self.skipped = False, '', 0, 0
        self.last_scan = 0
        with self.db() as db:
            db.executescript('''PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS files (path TEXT PRIMARY KEY, name TEXT, size INTEGER,
                    directory INTEGER, modified REAL, generation TEXT);
                CREATE VIRTUAL TABLE IF NOT EXISTS names USING fts5(name, path UNINDEXED, tokenize='trigram');
                CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
                    INSERT INTO names(rowid,name,path) VALUES(new.rowid,new.name,new.path); END;
                CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
                    DELETE FROM names WHERE rowid=old.rowid; END;
                CREATE TRIGGER IF NOT EXISTS files_au AFTER UPDATE ON files WHEN new.name IS NOT old.name BEGIN
                    DELETE FROM names WHERE rowid=old.rowid;
                    INSERT INTO names(rowid,name,path) VALUES(new.rowid,new.name,new.path); END;''')
            self.count = db.execute('SELECT count(*) FROM files').fetchone()[0]

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=2)
        db.execute('PRAGMA busy_timeout=2000')
        try:
            yield db
        finally:
            db.close()

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self.scan, name='vexx-file-index', daemon=True).start()
        return True

    def status(self):
        return {'running': self.running, 'paused': self.paused.is_set(), 'count': self.count,
                'skipped': self.skipped, 'error': self.error, 'last_scan': self.last_scan,
                'roots': [str(p) for p in self.roots]}

    def scan(self):
        generation, batch, sizes = uuid.uuid4().hex, [], {}
        self.count = 0
        self.error, self.skipped = '', 0
        try:
            with self.db() as db:
                stack = list(self.roots)
                while stack and not self.stop.is_set():
                    if self.paused.is_set():
                        self.stop.wait(.25)
                        continue
                    folder = stack.pop()
                    sizes.setdefault(str(folder), 0)
                    try:
                        with os.scandir(folder) as entries:
                            for entry in entries:
                                while self.paused.is_set() and not self.stop.is_set():
                                    self.stop.wait(.25)
                                if self.stop.is_set():
                                    break
                                if entry.is_symlink() or getattr(os.path, 'isjunction', lambda _: False)(entry.path):
                                    continue
                                try:
                                    directory = entry.is_dir(follow_symlinks=False)
                                    if directory and entry.name.casefold() in EXCLUDED:
                                        continue
                                    stat = entry.stat(follow_symlinks=False)
                                    if not directory:
                                        sizes[str(folder)] += stat.st_size
                                    batch.append((entry.path, entry.name, None if directory else stat.st_size,
                                                  int(directory), stat.st_mtime, generation))
                                    if directory:
                                        stack.append(Path(entry.path))
                                    if len(batch) >= 256:
                                        self._flush(db, batch)
                                        self.stop.wait(.025)  # yield disk and CPU between chunks
                                except (OSError, PermissionError):
                                    self.skipped += 1
                    except (OSError, PermissionError):
                        self.skipped += 1
                self._flush(db, batch)
                if not self.stop.is_set():
                    db.execute('DELETE FROM files WHERE generation<>?', (generation,))
                    # Aggregate once after the scan. Never recurse or stat on a query.
                    for folder in sorted(sizes, key=len, reverse=True):
                        parent = str(Path(folder).parent)
                        if parent in sizes and parent != folder:
                            sizes[parent] += sizes[folder]
                    db.executemany('UPDATE files SET size=? WHERE path=? AND directory=1',
                                   ((size, folder) for folder, size in sizes.items()))
                    db.commit()
                    self.last_scan = time.time()
                self.count = db.execute('SELECT count(*) FROM files').fetchone()[0]
        except (OSError, sqlite3.Error) as exc:
            self.error = type(exc).__name__ + ': não foi possível concluir o índice.'
        finally:
            self.running = False

    def _flush(self, db, batch):
        if not batch:
            return
        db.executemany('''INSERT INTO files VALUES (?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
            name=excluded.name,size=excluded.size,directory=excluded.directory,
            modified=excluded.modified,generation=excluded.generation''', batch)
        db.commit()
        self.count += len(batch)
        batch.clear()

    def search(self, query='', offset=0, kind='all'):
        started = time.perf_counter()
        query = query.strip()[:160]
        offset = max(0, min(int(offset), 100000))
        params, where = [], []
        source = 'files f'
        if len(query) >= 3:
            source += ' JOIN names n ON n.rowid=f.rowid'
            where.append('names MATCH ?')
            params.append('"' + query.replace('"', '""') + '"')
        elif query:
            return {'items': [], 'more': False, 'ms': 0, 'hint': 'Digite pelo menos 3 caracteres.', **self.status()}
        if kind in ('files', 'folders'):
            where.append('f.directory=?')
            params.append(int(kind == 'folders'))
        sql = 'SELECT f.path,f.name,f.size,f.directory,f.modified FROM ' + source
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        # No count(*) or full result sort; only a bounded page is read.
        sql += ' LIMIT 61 OFFSET ?'
        with self.db() as db:
            db.set_progress_handler(lambda: int(time.perf_counter() - started > .15), 1000)
            try:
                rows = db.execute(sql, (*params, offset)).fetchall()
            except sqlite3.OperationalError:
                return {'items': [], 'more': False, 'ms': round((time.perf_counter()-started)*1000),
                        'hint': 'Busca interrompida pelo limite de tempo. Refine o nome.', **self.status()}
        return {'items': [dict(zip(('path', 'name', 'size', 'directory', 'modified'), row)) for row in rows[:60]],
                'more': len(rows) > 60, 'ms': round((time.perf_counter() - started) * 1000, 1), **self.status()}
