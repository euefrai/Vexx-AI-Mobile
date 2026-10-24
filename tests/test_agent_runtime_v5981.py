import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest
import agent_runtime as ar


def test_os_lock_ownership_stale_metadata_and_reuse(tmp_path):
    path = tmp_path/'lock'
    first = ar.InstanceLock(path).acquire()
    try:
        with pytest.raises(RuntimeError):
            ar.InstanceLock(path).acquire()
        script = 'import agent_runtime as a; a.InstanceLock(__import__("sys").argv[1]).acquire()'
        r = subprocess.run([sys.executable, '-c', script, str(path)], capture_output=True)
        assert r.returncode != 0
    finally:
        first.close()
    path.write_text('stale pid 123 reused')
    ar.InstanceLock(path).acquire().close()


def test_identity_and_isolated_development():
    assert ar.identity('https://example.org/') == ar.identity('https://example.org')
    assert ar.identity('http://localhost:8000','development') != ar.identity('https://example.org')
    with pytest.raises(ValueError):
        ar.identity('https://example.org', 'development')
    with pytest.raises(ValueError):
        ar.identity('https://secret@example.org')


def test_real_local_authenticated_channel_and_drain_timeout(tmp_path):
    r = ar.Runtime('http://localhost:12345', directory=tmp_path/'runtime').start()
    try:
        assert ar.command(r.directory)['pid'] == os.getpid()
        assert ar.command(r.directory, 'shell')['error'] == 'unsupported_action'
        r.drain = lambda: False
        result = ar.command(r.directory, 'stop', timeout=1)
        assert result['state'] in ('STOP_ACCEPTED','STOPPING_NEW_JOBS','DRAINING')
        time.sleep(1.3)
        assert r.state == 'BLOCKED_DRAIN_TIMEOUT'
        with pytest.raises(RuntimeError):
            with r.operation():
                pass
        with pytest.raises(RuntimeError):
            ar.InstanceLock(r.directory/'instance.lock').acquire()
    finally:
        r.close()


def test_wrong_key_and_stale_process_are_rejected(tmp_path):
    r = ar.Runtime('http://localhost:23456', directory=tmp_path/'runtime').start()
    try:
        keyfile = r.directory/'control.key'
        original = keyfile.read_bytes()
        keyfile.write_bytes(b'x'*32)
        assert ar.command(r.directory)['error'] == 'unauthorized'
        keyfile.write_bytes(original)
        status = r.directory/'status.json'
        data = json.loads(status.read_text()); data['generation'] = 'old-pid'
        status.write_text(json.dumps(data))
        assert ar.command(r.directory)['error'] == 'stale_process'
    finally:
        r.close()


def test_operation_finishes_without_force(tmp_path):
    r = ar.Runtime('http://localhost:34567', directory=tmp_path/'runtime').start()
    finished = threading.Event()
    class Connection:
        def close(self):
            finished.set()
    r.connection = Connection()
    try:
        with r.operation():
            ar.command(r.directory,'stop',timeout=2)
            assert not finished.wait(.2)
        assert finished.wait(2)
    finally:
        r.close()
