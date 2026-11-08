"""Nonblocking hardware samples, low-RAM working-set trimmer and local network diagnostics."""
import gc
import os
import platform
import socket
import subprocess
import time
from urllib.parse import urlsplit

import psutil

PROTECTED_PROCESSES = {
    'system', 'registry', 'memory compression', 'idle', 'system interrupts',
    'csrss.exe', 'wininit.exe', 'services.exe', 'lsass.exe', 'smss.exe', 'winlogon.exe', 'dwm.exe',
}


def _trim_pid_working_set(pid):
    if os.name != 'nt':
        return False
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi.EmptyWorkingSet.argtypes = [wintypes.HANDLE]
    psapi.EmptyWorkingSet.restype = wintypes.BOOL
    # PROCESS_QUERY_INFORMATION (0x0400) | PROCESS_SET_QUOTA (0x0100)
    handle = kernel.OpenProcess(0x0400 | 0x0100, False, int(pid))
    if not handle:
        return False
    try:
        return bool(psapi.EmptyWorkingSet(handle))
    finally:
        kernel.CloseHandle(handle)


def trim_self_memory(include_children=True):
    """Release unused Python heap and Windows working-set pages for Vexx PC."""
    gc.collect()
    if os.name != 'nt':
        return
    my_pid = os.getpid()
    if include_children:
        try:
            for child in psutil.Process(my_pid).children(recursive=True):
                _trim_pid_working_set(child.pid)
        except psutil.Error:
            pass
    _trim_pid_working_set(my_pid)


def optimize_system_memory():
    """Safely trim unused working-set pages across user processes without closing apps."""
    gc.collect()
    before_mem = psutil.virtual_memory()
    before_agent = psutil.Process(os.getpid()).memory_info().rss
    trimmed = 0
    if os.name == 'nt':
        for proc in psutil.process_iter(('pid', 'name', 'memory_info')):
            try:
                info = proc.info
                name = (info.get('name') or '').casefold()
                mem = info.get('memory_info')
                if not mem or name in PROTECTED_PROCESSES:
                    continue
                if info['pid'] == os.getpid() or mem.rss >= 32 * 1024 * 1024:
                    if _trim_pid_working_set(info['pid']):
                        trimmed += 1
            except (psutil.Error, OSError):
                continue
        trim_self_memory(include_children=True)
    after_mem = psutil.virtual_memory()
    after_agent = psutil.Process(os.getpid()).memory_info().rss
    freed = max(0, before_mem.used - after_mem.used)
    agent_saved = max(0, before_agent - after_agent)
    return {
        'freed': max(freed, agent_saved),
        'freed_bytes': max(freed, agent_saved),
        'trimmed_processes': trimmed,
        'ram_before': before_mem.used,
        'ram_after': after_mem.used,
        'ram_percent': after_mem.percent,
        'after': {'used': after_mem.used, 'percent': after_mem.percent},
        'agent_rss': after_agent,
    }


def listening_ports():
    """List local TCP listening ports with owning process names."""
    items = []
    seen = set()
    try:
        connections = psutil.net_connections(kind='tcp')
    except (psutil.Error, OSError):
        return []
    for conn in connections:
        if conn.status != psutil.CONN_LISTEN or not conn.laddr:
            continue
        port = conn.laddr.port
        ip = conn.laddr.ip
        key = (ip, port)
        if key in seen:
            continue
        seen.add(key)
        name = 'Sistema'
        if conn.pid:
            try:
                name = psutil.Process(conn.pid).name()[:80]
            except (psutil.Error, OSError):
                name = f'PID {conn.pid}'
        is_loopback = ip in ('127.0.0.1', '::1')
        items.append({
            'port': port,
            'address': ip,
            'pid': conn.pid or 0,
            'name': name,
            'process': name,
            'local_only': is_loopback,
            'loopback': is_loopback,
        })
    items.sort(key=lambda x: (not x['local_only'], x['port']))
    return items[:50]


def flush_dns():
    if os.name != 'nt':
        return {'ok': False, 'message': 'Limpeza de DNS nativa disponível apenas no Windows.'}
    try:
        res = subprocess.run(
            ['ipconfig', '/flushdns'],
            capture_output=True,
            timeout=6,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        return {
            'ok': res.returncode == 0,
            'message': 'Cache DNS do Windows limpo com sucesso.' if res.returncode == 0 else 'Não foi possível limpar o cache DNS.',
        }
    except (OSError, subprocess.TimeoutExpired):
        return {'ok': False, 'message': 'Tempo esgotado ao limpar o cache DNS.'}


def network_diagnostics(relay=''):
    """Run fast, bounded local connectivity and DNS checks."""
    host = urlsplit(relay).hostname if relay else 'vexx-ai.onrender.com'
    dns_ms = None
    dns_ok = False
    resolved_ip = ''
    if host:
        started = time.perf_counter()
        try:
            infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            if infos:
                dns_ok = True
                resolved_ip = str(infos[0][4][0])
                dns_ms = round((time.perf_counter() - started) * 1000, 1)
        except OSError:
            dns_ok = False
    ports = listening_ports()
    checks = [{'target': host or 'localhost', 'ok': dns_ok, 'ip': resolved_ip, 'latency_ms': dns_ms}]
    return {
        'target_host': host or '',
        'dns_ok': dns_ok,
        'dns_ms': dns_ms,
        'resolved_ip': resolved_ip,
        'all_ok': dns_ok,
        'checks': checks,
        'listening_count': len(ports),
        'exposed_ports': sum(1 for p in ports if not p.get('loopback')),
        'ports': ports[:15],
        'checked_at': time.time(),
    }


class SystemMonitor:
    def __init__(self):
        psutil.cpu_percent(None)
        self.previous = None
        self.ssid, self.ssid_at = '', 0
        self.processes_at, self.heavy_processes = 0, []
        self.trimmed_at = 0

    def snapshot(self):
        now = time.monotonic()
        if now - self.trimmed_at >= 45:
            self.trimmed_at = now
            trim_self_memory(include_children=False)
        memory = psutil.virtual_memory()
        disks = []
        for part in psutil.disk_partitions(all=False):
            if 'cdrom' in part.opts or part.fstype == '':
                continue
            # Skip mapped/removable network volumes; a sleeping share may block stat.
            if part.mountpoint.startswith(('\\\\', '//')) or 'remote' in part.opts:
                continue
            try:
                used = psutil.disk_usage(part.mountpoint)
                disks.append({'path': part.mountpoint, 'total': used.total, 'used': used.used,
                              'free': used.free, 'percent': used.percent})
            except OSError:
                continue
        counters = psutil.net_io_counters()
        rates = {'download': 0, 'upload': 0}
        if self.previous:
            at, received, sent = self.previous
            elapsed = max(.01, now - at)
            rates = {'download': max(0, (counters.bytes_recv - received) / elapsed),
                     'upload': max(0, (counters.bytes_sent - sent) / elapsed)}
        self.previous = (now, counters.bytes_recv, counters.bytes_sent)
        adapters = []
        stats = psutil.net_if_stats()
        for name, addresses in psutil.net_if_addrs().items():
            stat = stats.get(name)
            if not stat or not stat.isup:
                continue
            ips = [a.address for a in addresses if a.family in (socket.AF_INET, socket.AF_INET6)
                   and not a.address.startswith(('127.', '::1'))]
            if ips:
                adapters.append({'name': name, 'addresses': ips, 'speed_mbps': stat.speed})
        battery = psutil.sensors_battery()
        if os.name == 'nt' and now - self.ssid_at > 30:
            self.ssid_at = now
            try:
                import re
                output = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], capture_output=True,
                                        timeout=2, creationflags=subprocess.CREATE_NO_WINDOW)
                match = re.search(r'^\s*SSID\s*:\s*(.+)$', output.stdout.decode(errors='replace'), re.MULTILINE)
                self.ssid = match.group(1).strip() if match else ''
            except (OSError, subprocess.TimeoutExpired):
                self.ssid = ''
        if now - self.processes_at >= 30:
            processes = []
            for proc in psutil.process_iter(('pid', 'name', 'memory_info', 'create_time')):
                try:
                    info = proc.info
                    memory_info = info.get('memory_info')
                    if not memory_info or not info.get('name'):
                        continue
                    processes.append({'pid': info['pid'], 'name': info['name'][:120],
                                      'rss': memory_info.rss, 'created': info.get('create_time')})
                except (psutil.Error, OSError):
                    continue
            apps = {}
            for proc in processes:
                name = proc['name'].casefold()
                if name in ('system', 'registry', 'memory compression', 'idle', 'system interrupts') or proc['pid'] == os.getpid():
                    continue
                item = apps.setdefault(name, {'name': proc['name'], 'rss': 0, 'processes': []})
                item['rss'] += proc['rss']
                item['processes'].append({'pid': proc['pid'], 'created': proc['created']})
            self.heavy_processes = sorted(apps.values(), key=lambda p: p['rss'], reverse=True)[:8]
            self.processes_at = now
        heavy = self.heavy_processes
        return {'name': platform.node(), 'os': platform.platform(), 'cpu_percent': psutil.cpu_percent(None),
                'cpu_cores': psutil.cpu_count(), 'ram': {'used': memory.used, 'total': memory.total, 'percent': memory.percent},
                'uptime': max(0, time.time() - psutil.boot_time()), 'disks': disks, 'adapters': adapters,
                'network': rates, 'ssid': self.ssid,
                'battery': None if not battery else {'percent': battery.percent, 'plugged': battery.power_plugged},
                'agent_rss': psutil.Process(os.getpid()).memory_info().rss, 'processes': heavy, 'sampled_at': time.time()}
