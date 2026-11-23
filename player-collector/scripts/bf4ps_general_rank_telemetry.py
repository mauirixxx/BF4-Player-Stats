#!/usr/bin/env python3
"""LAN-only read-only BF4PS ranking host telemetry (no database credentials)."""
import json,os,time,subprocess
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
HOST='192.168.10.66'
ALLOW={'192.168.10.71','127.0.0.1'}
def read(path):
    try:return Path(path).read_text()
    except OSError:return ''
def cpu_sample():
    fields=read('/proc/stat').splitlines()[0].split()[1:]
    values=[int(v) for v in fields]
    return sum(values),values[3]+values[4]
LAST_CPU=None
def proc_status():
    # The active publisher is a child of the refresh runner; inspect process command lines, not uncommitted DB rows.
    for pid in os.listdir('/proc'):
        if not pid.isdigit():continue
        raw=read('/proc/'+pid+'/cmdline').replace('\0',' ')
        if 'bf4ps.general_rank_publisher' not in raw or ' --execute' not in raw:continue
        parts=raw.split()
        try:
            metric=parts[parts.index('--metric')+1]
            platform=parts[parts.index('--platform')+1]
            stat=read('/proc/'+pid+'/stat').split()
            uptime=float(read('/proc/uptime').split()[0])
            elapsed=max(0,uptime-int(stat[21])/os.sysconf('SC_CLK_TCK'))
            return {'metric':metric,'platform':platform,'elapsed_seconds':round(elapsed),'pid':int(pid)}
        except (ValueError,IndexError,OSError):continue
    return None
def status():
    global LAST_CPU
    sample=cpu_sample()
    percent=None
    if LAST_CPU:
        dt=sample[0]-LAST_CPU[0]
        if dt>0:percent=round(100*(1-(sample[1]-LAST_CPU[1])/dt),1)
    LAST_CPU=sample
    runner=False
    for pid in os.listdir('/proc'):
        if not pid.isdigit():continue
        raw=read('/proc/'+pid+'/cmdline').replace('\0',' ')
        if '/usr/local/sbin/bf4ps-general-rank-refresh.py' in raw:
            runner=True
            break
    service='active' if runner else 'inactive'
    timer='enabled' if Path('/etc/systemd/system/timers.target.wants/bf4ps-general-rank-refresh.timer').exists() else 'disabled'
    mem={}
    for line in read('/proc/meminfo').splitlines():
        k,_,v=line.partition(':')
        if k in ('MemTotal','MemAvailable','SwapTotal','SwapFree'):
            mem[k]=int(v.split()[0])*1024
    disk=os.statvfs('/fast/pgdata')
    return {'observed_at':time.time(),'hostname':os.uname().nodename,'service':service,'timer':timer,
        'current':proc_status(),'load_1_5_15':list(os.getloadavg()),'cpu_count':os.cpu_count(),'cpu_percent':percent,
        'memory_total':mem.get('MemTotal'),'memory_available':mem.get('MemAvailable'),
        'swap_used':mem.get('SwapTotal',0)-mem.get('SwapFree',0),
        'disk_free':disk.f_bavail*disk.f_frsize,'disk_total':disk.f_blocks*disk.f_frsize}
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.client_address[0] not in ALLOW or self.path!='/status':
            self.send_error(403);return
        payload=json.dumps(status()).encode()
        self.send_response(200)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers();self.wfile.write(payload)
    def log_message(self,*args):pass
if __name__=='__main__':
    ThreadingHTTPServer((HOST,8769),Handler).serve_forever()
