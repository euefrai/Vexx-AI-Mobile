"""Nonblocking hardware samples; network adapters do not imply Internet access."""
import os
import platform
import socket
import time
import subprocess

import psutil


class SystemMonitor:
    def __init__(self):
        psutil.cpu_percent(None)
        self.previous = None
        self.ssid, self.ssid_at = '', 0

    def snapshot(self):
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
        counters, now = psutil.net_io_counters(), time.monotonic()
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
        return {'name': platform.node(), 'os': platform.platform(), 'cpu_percent': psutil.cpu_percent(None),
                'cpu_cores': psutil.cpu_count(), 'ram': {'used': memory.used, 'total': memory.total, 'percent': memory.percent},
                'uptime': max(0, time.time() - psutil.boot_time()), 'disks': disks, 'adapters': adapters,
                'network': rates, 'ssid': self.ssid, 'battery': None if not battery else {'percent': battery.percent, 'plugged': battery.power_plugged},
                'agent_rss': psutil.Process(os.getpid()).memory_info().rss, 'sampled_at': time.time()}
