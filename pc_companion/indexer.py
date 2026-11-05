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
            '.git', '.venv', '.vexx-venv', '__pycache__', '.cache', 'appdata', 'programdata', '.vexx-trash'}


class FileIndex:
    def __init__(self, path, roots):
        self.path, self.roots = Path(path), [Path(p).resolve() for p in roots]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.write_lock = threading.RLock()
        self.removed = set()
        self.generation = 'manual'
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
            columns={row[1] for row in db.execute('PRAGMA table_info(files)')}
            for column in ('parent','extension'):
                if column not in columns:db.execute('ALTER TABLE files ADD COLUMN '+column+' TEXT')
            db.executescript('''CREATE INDEX IF NOT EXISTS files_size ON files(directory,size DESC,path);
                CREATE INDEX IF NOT EXISTS files_age ON files(directory,modified,path);
                CREATE INDEX IF NOT EXISTS files_extension ON files(extension,size DESC,path);
                CREATE INDEX IF NOT EXISTS files_parent ON files(parent,name COLLATE NOCASE,path);''')
        self.migrating=True
        threading.Thread(target=self._metadata,name='vexx-index-metadata',daemon=True).start()

    def _metadata(self):
        try:
            with self.db() as db:
                while not self.stop.is_set():
                    rows=db.execute('SELECT path FROM files WHERE parent IS NULL LIMIT 1000').fetchall()
                    if not rows:break
                    db.executemany('UPDATE files SET parent=?,extension=? WHERE path=? AND parent IS NULL',
                        ((str(Path(p).parent),Path(p).suffix.casefold(),p) for (p,) in rows));db.commit()
                    self.stop.wait(.025)
        except sqlite3.Error:
            pass  # The normal background scan also fills the metadata.
        finally:self.migrating=False

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
                'roots': [str(p) for p in self.roots], 'migrating':self.migrating}

    def scan(self):
        generation, batch, sizes = uuid.uuid4().hex, [], {}
        with self.write_lock:
            self.generation=generation;self.removed.clear()
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
        with self.write_lock:
            db.executemany('''INSERT INTO files(path,name,size,directory,modified,generation,parent,extension) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(path) DO UPDATE SET
                name=excluded.name,size=excluded.size,directory=excluded.directory,
                modified=excluded.modified,generation=excluded.generation,parent=excluded.parent,extension=excluded.extension''',
                ((*row,str(Path(row[0]).parent),Path(row[0]).suffix.casefold()) for row in batch if row[0] not in self.removed))
            db.commit()
        self.count += len(batch)
        batch.clear()

    def search(self, query='', offset=0, kind='all', sort='relevance', min_size=0, age_days=0, folder=''):
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
        else:
            from .files import CATEGORIES
            if kind in CATEGORIES:
                extensions=sorted(CATEGORIES[kind]);where.append('f.directory=0 AND f.extension IN ('+','.join('?' for _ in extensions)+')');params.extend(extensions)
        if min_size:
            where.append('f.size>=?');params.append(max(0,min(int(min_size),10**15)))
        if age_days:
            where.append('f.modified<=?');params.append(time.time()-max(0,min(int(age_days),36500))*86400)
        if folder:
            where.append('f.parent=?');params.append(str(Path(folder)))
        sql = 'SELECT f.path,f.name,f.size,f.directory,f.modified FROM ' + source
        if where:
            sql += ' WHERE ' + ' AND '.join(where)
        order={'name':'f.name COLLATE NOCASE,f.path','largest':'f.size DESC,f.path','smallest':'f.size,f.path',
               'newest':'f.modified DESC,f.path','oldest':'f.modified,f.path'}
        if sort in order:sql += ' ORDER BY '+order[sort]
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
