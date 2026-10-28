"""Local process ownership and authenticated maintenance; never a remote shell.

Windows uses an OS file lock and a current-user-only directory with named pipes.
The backend may be an independently pinned published checkout.
"""
import argparse
import contextlib
import hashlib
import hmac
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import threading
import time
from multiprocessing.connection import Client, Listener
from urllib.parse import urlsplit


def identity(relay, role="production", instance="default"):
    parsed = urlsplit(relay)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Relay não pode conter credenciais/parâmetros")
    if role not in ("production", "development"):
        raise ValueError("Papel de runtime inválido")
    if role == 'production' and instance != 'default':
        raise ValueError('Produção permite uma única instância por relay')
    if role == "development" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Desenvolvimento exige relay local isolado")
    # The DB is deliberately excluded: two DBs must not consume the same relay.
    value = f"{parsed.scheme.lower()}://{parsed.netloc.lower()}{parsed.path.rstrip('/')}|{role}|{instance}"
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def private_directory(path):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        sid = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True).strip().split(',')[-1].strip('"')
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        path.chmod(0o700)
    return path


def process_created():
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetCurrentProcess.restype=wintypes.HANDLE
    kernel.GetProcessTimes.argtypes=[wintypes.HANDLE]+[ctypes.POINTER(wintypes.FILETIME)]*4
    values=[wintypes.FILETIME() for _ in range(4)]
    if not kernel.GetProcessTimes(kernel.GetCurrentProcess(),*[ctypes.byref(v) for v in values]):
        raise ctypes.WinError(ctypes.get_last_error())
    return ((values[0].dwHighDateTime<<32)|values[0].dwLowDateTime)/10_000_000-11644473600


class InstanceLock:
    def __init__(self, path):
        self.path = Path(path)
        self.file = None

    def acquire(self):
        self.file = self.path.open("a+b")
        self.file.seek(0, 2)
        if self.file.tell() == 0:
            self.file.write(b"0"); self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.file.close(); self.file = None
            raise RuntimeError("Instância ativa já possui este papel e relay") from None
        return self

    def close(self):
        if self.file:
            self.file.close(); self.file = None


class Runtime:
    def __init__(self, relay, role="production", instance="default", directory=None):
        key = identity(relay, role, instance)
        self.directory = private_directory(directory or Path.home()/".julia-mobile"/"runtime"/key)
        self.lock = InstanceLock(self.directory/"instance.lock")
        self.pid = os.getpid()
        self.created = process_created()
        self.started = self.created if self.created is not None else time.time()
        self.generation = secrets.token_hex(16)
        self.role = role
        self.channel_id = (hashlib.sha256((str(self.directory.resolve())+key).encode()).hexdigest()[:24]
                           if directory is not None else key)
        self.state = "STARTING"
        self.stop = threading.Event()
        self.finished = threading.Event()
        self.active = 0
        self.guard = threading.Lock()
        self.connection = None
        self.listener = None
        self.secret = None
        self.drain = lambda: True
        self.address = (r"\\.\pipe\vexx-"+self.channel_id) if os.name == "nt" else str(self.directory/"control.sock")
        self.family = "AF_PIPE" if os.name == "nt" else "AF_UNIX"

    def snapshot(self):
        return {"pid": self.pid, "ppid": os.getppid(), "started": self.started, "process_created":self.created, "generation": self.generation,
                "role": self.role, "channel_id": self.channel_id, "state": self.state, "uptime_s": round(time.time()-self.started),
                "active_operations": self.active}

    def transition(self, state):
        self.state = state
        target = self.directory/"status.json"
        temp = target.with_suffix(".tmp")
        temp.write_text(json.dumps(self.snapshot()), encoding="utf-8")
        os.replace(temp, target)

    def start(self):
        self.lock.acquire()
        try:
            self.secret = secrets.token_bytes(32)
            (self.directory/"control.key").write_bytes(self.secret)
            if os.name != "nt":
                Path(self.address).unlink(missing_ok=True)
            self.listener = Listener(self.address, family=self.family, authkey=None)
            self.transition("RUNNING")
            threading.Thread(target=self._serve, name="vexx-local-control", daemon=True).start()
            return self
        except BaseException:
            self.lock.close()
            raise

    @contextlib.contextmanager
    def operation(self, accepted=False):
        with self.guard:
            if self.stop.is_set() and not accepted:
                raise RuntimeError("Agente em manutenção")
            self.active += 1
        try:
            yield
        finally:
            with self.guard:
                self.active -= 1

    def _serve(self):
        while not self.finished.is_set():
            try:
                with self.listener.accept() as channel:
                    nonce = secrets.token_hex(32)
                    channel.send_bytes(nonce.encode())
                    if not channel.poll(2):
                        continue
                    data = json.loads(channel.recv_bytes(4096))
                    if not isinstance(data,dict):
                        channel.send_bytes(b'{"error":"invalid_request"}')
                        continue
                    action = data.get("action", "")
                    expected = hmac.new(self.secret, (nonce+":"+action).encode(), "sha256").hexdigest()
                    if not hmac.compare_digest(str(data.get("proof", "")), expected):
                        channel.send_bytes(b'{"error":"unauthorized"}')
                        continue
                    if data.get("generation") != self.generation or data.get("pid") != self.pid or data.get('process_created') != self.created:
                        channel.send_bytes(b'{"error":"stale_process"}')
                        continue
                    if action == "status":
                        channel.send_bytes(json.dumps(self.snapshot()).encode())
                    elif action == "stop":
                        timeout = min(120, max(1, float(data.get("timeout", 30))))
                        if not self.stop.is_set() or self.state == "BLOCKED_DRAIN_TIMEOUT":
                            self.transition("STOP_REQUESTED")
                            self.stop.set()
                            self.transition("STOP_ACCEPTED")
                            threading.Thread(target=self._drain, args=(timeout,), daemon=True).start()
                        channel.send_bytes(json.dumps(self.snapshot()).encode())
                    else:
                        channel.send_bytes(b'{"error":"unsupported_action"}')
            except (OSError, EOFError, ValueError, TypeError):
                if self.finished.is_set():
                    return

    def _drain(self, timeout):
        self.transition("STOPPING_NEW_JOBS")
        self.transition("DRAINING")
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline and not self.finished.is_set():
            if self.active == 0 and self.drain():
                if self.connection is not None:
                    self.connection.close()
                return
            self.finished.wait(.1)
        # No force exit and no lock release while a worker can still write.
        if not self.finished.is_set():
            self.transition("BLOCKED_DRAIN_TIMEOUT")

    def close(self):
        self.finished.set()
        self.transition("STOPPED")
        if self.listener:
            self.listener.close()
        self.lock.close()


def command(directory, action="status", timeout=30):
    directory = Path(directory)
    data = json.loads((directory/"status.json").read_text(encoding="utf-8"))
    key = data["channel_id"]
    address = (r"\\.\pipe\vexx-"+key) if os.name == "nt" else str(directory/"control.sock")
    with Client(address, family="AF_PIPE" if os.name == "nt" else "AF_UNIX", authkey=None) as channel:
        if not channel.poll(3):
            raise TimeoutError("Canal local não respondeu")
        nonce = channel.recv_bytes(128).decode()
        secret = (directory/"control.key").read_bytes()
        proof = hmac.new(secret, (nonce+":"+action).encode(), "sha256").hexdigest()
        channel.send_bytes(json.dumps({"action":action, "pid":data["pid"],
                         "generation":data["generation"], "process_created":data.get('process_created'), "proof":proof, "timeout":timeout}).encode())
        if not channel.poll(3):
            raise TimeoutError("Operação local não respondeu")
        return json.loads(channel.recv_bytes(4096))


def launch(module):
    """Wrap a pinned backend without editing its source or replacing its jobs."""
    role = os.getenv("VEXX_AGENT_ROLE", "production")
    if role == "development":
        path=os.getenv('JULIA_SQLITE_PATH','')
        if not path or Path(path).resolve() == (Path.home()/'.julia-mobile'/'memory.sqlite3').resolve():
            raise ValueError('Desenvolvimento exige SQLite explícito e isolado')
    runtime = Runtime(os.environ["JULIA_RELAY_URL"], role, os.getenv("VEXX_AGENT_INSTANCE", "default"),
                      directory=os.getenv('VEXX_AGENT_RUNTIME_DIR') if role=='development' else None).start()
    module.VEXX_RUNTIME = runtime
    original_connect = module.connect
    original_threading = module.threading
    class ManagedThread(threading.Thread):
        def start(self):
            with runtime.guard:
                runtime.active += 1
            try:
                return super().start()
            except BaseException:
                with runtime.guard:
                    runtime.active -= 1
                raise
        def run(self):
            try:
                super().run()
            finally:
                with runtime.guard:
                    runtime.active -= 1
    class ManagedThreading:
        Thread = ManagedThread
        def __getattr__(self, name):
            return getattr(original_threading, name)
    module.threading = ManagedThreading()
    original_pools = []
    for pool_name in ("_SINT_POOL", "_SCREEN_POOL"):
        pool = getattr(module, pool_name, None)
        if pool is None: continue
        original_submit = pool.submit
        original_pools.append((pool, original_submit))
        def submit(*args, _original_submit=original_submit, **kwargs):
            with runtime.guard:
                runtime.active += 1
            try:
                future = _original_submit(*args, **kwargs)
            except BaseException:
                with runtime.guard:
                    runtime.active -= 1
                raise
            def done(_):
                with runtime.guard:
                    runtime.active -= 1
            future.add_done_callback(done)
            return future
        pool.submit = submit
    original_time = module.time
    class InterruptibleTime:
        def __getattr__(self, name):
            return getattr(original_time, name)
        def sleep(self, seconds):
            runtime.stop.wait(seconds)
    module.time = InterruptibleTime()
    workers = ("ai_stream_worker", "_job_worker", "aprender_com_conversa", "_sintetizar_isolado")
    originals = {name:getattr(module, name) for name in workers if hasattr(module, name)}
    for name, fn in originals.items():
        def wrapped(*args, _fn=fn, **kwargs):
            with runtime.operation(accepted=True):
                return _fn(*args, **kwargs)
        setattr(module, name, wrapped)

    def drained():
        # Workers finish/checkpoint using their original published code.
        return runtime.active == 0
    runtime.drain = drained

    class ControlledConnection:
        def __init__(self, *args, **kwargs):
            if runtime.stop.is_set():
                raise KeyboardInterrupt
            self.inner = original_connect(*args, **kwargs)
        def __enter__(self):
            runtime.connection = self.inner.__enter__()
            return self
        def __exit__(self, *args):
            runtime.connection = None
            return self.inner.__exit__(*args)
        def send(self, *args, **kwargs):
            return self.inner.send(*args, **kwargs)
        def __iter__(self):
            for raw in self.inner:
                if runtime.stop.is_set():
                    try:
                        request=json.loads(raw)
                        if not isinstance(request,dict):
                            continue
                        request_id=request.get('request_id')
                        if isinstance(request_id,str):
                            with module.ENVIO_LOCK:
                                self.inner.send(json.dumps({'request_id':request_id,'type':'op_error',
                                    'codigo':'manutencao','error':'PC Agent em manutenção; tente novamente após reconectar.'}))
                    except (ValueError,TypeError):
                        pass
                    continue
                try:
                    with runtime.operation():
                        yield raw
                except RuntimeError:
                    if runtime.stop.is_set():
                        raise KeyboardInterrupt
                    raise

    module.connect = ControlledConnection
    try:
        module.run()
    finally:
        # run() closes its main DB; workers have drained before closing the WSS.
        if runtime.active:
            runtime.transition("BLOCKED_ACTIVE_WORKERS")
        else:
            runtime.transition("SQLITE_FLUSH")
            import sqlite3
            db = sqlite3.connect(module.database_path(), timeout=5)
            db.execute("PRAGMA wal_checkpoint(PASSIVE)"); db.close()
            runtime.transition("CONNECTION_CLOSE")
            runtime.close()
        module.connect = original_connect
        module.threading = original_threading
        module.time = original_time
        for saved_pool, saved_submit in original_pools:
            saved_pool.submit = saved_submit
        for name, fn in originals.items():
            setattr(module, name, fn)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--script", type=Path)
    parser.add_argument("--control", type=Path)
    parser.add_argument("--action", choices=("status", "stop"), default="status")
    args = parser.parse_args()
    if args.control:
        print(json.dumps(command(args.control, args.action)))
    elif args.script:
        script = args.script.resolve()
        sys.path.insert(0, str(script.parent))
        spec = importlib.util.spec_from_file_location("pc_agent", script)
        module = importlib.util.module_from_spec(spec)
        sys.modules["pc_agent"] = module
        spec.loader.exec_module(module)
        launch(module)
    else:
        parser.error("Informe --script ou --control")
