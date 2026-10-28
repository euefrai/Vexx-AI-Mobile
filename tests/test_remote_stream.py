"""Remote interaction regressions; native input is mocked, never controls the operator."""
import ctypes
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace
import pytest
import remoto
from server import InputBody

@pytest.mark.parametrize('points', [[], [{}], [{'x':float('nan'),'y':0}]*2, [{'x':2,'y':0}]*2, [{'x':0,'y':0}]*33, [None,None]])
def test_invalid_drag(points):
    with pytest.raises(remoto.RemotoErro):
        remoto.validar_comando({'kind':'drag','points':points})

def test_drag_releases_button_after_native_failure(monkeypatch):
    events=[]
    def move(x,y):
        if x == 90: raise RuntimeError('native failure')
    native=SimpleNamespace(SetCursorPos=move,mouse_event=lambda *a:events.append(a[0]))
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=native),raising=False)
    monkeypatch.setattr(remoto.sys,'platform','win32')
    monkeypatch.setattr(remoto,'checar_ritmo',lambda:None)
    monkeypatch.setattr(remoto,'_para_px',lambda x,y:(int(x*100),int(y*100)))
    cmd=remoto.validar_comando(InputBody(kind='drag',points=[{'x':0,'y':0},{'x':.9,'y':.9}]).model_dump())
    with pytest.raises(RuntimeError): remoto.executar(cmd,autorizado=True)
    assert events == [2,4]

def test_horizontal_scroll(monkeypatch):
    events=[]
    monkeypatch.setattr(ctypes,'windll',SimpleNamespace(user32=SimpleNamespace(mouse_event=lambda *a:events.append(a))),raising=False)
    monkeypatch.setattr(remoto.sys,'platform','win32')
    monkeypatch.setattr(remoto,'checar_ritmo',lambda:None)
    remoto.executar({'kind':'scroll','dx':2,'dy':-3},autorizado=True)
    assert [(e[0],e[3]) for e in events] == [(0x0800,-360),(0x1000,240)]

def test_mobile_gestures_and_frame_lifecycle():
    node=shutil.which('node')
    if not node: pytest.skip('Node unavailable')
    run=subprocess.run([node,'tools/test_remote_stream.cjs'],cwd=Path(__file__).resolve().parents[1],capture_output=True,text=True)
    assert run.returncode == 0, run.stdout+run.stderr
