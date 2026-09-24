import ctypes as C,time,datetime,json
from ctypes import wintypes as W
K=C.WinDLL('kernel32',use_last_error=True);P=C.WinDLL('psapi',use_last_error=True)
class PE(C.Structure):
 _fields_=[('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',C.c_size_t),('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),('priority',W.LONG),('flags',W.DWORD),('name',W.WCHAR*260)]
class FT(C.Structure):_fields_=[('low',W.DWORD),('high',W.DWORD)]
class MEM(C.Structure):_fields_=[('cb',W.DWORD),('faults',W.DWORD),('peak',C.c_size_t),('ws',C.c_size_t),('qpp',C.c_size_t),('qp',C.c_size_t),('qnp',C.c_size_t),('qn',C.c_size_t),('page',C.c_size_t),('peakpage',C.c_size_t)]
K.CreateToolhelp32Snapshot.restype=W.HANDLE;K.OpenProcess.restype=W.HANDLE
K.Process32FirstW.argtypes=[W.HANDLE,C.POINTER(PE)];K.Process32NextW.argtypes=[W.HANDLE,C.POINTER(PE)];K.CloseHandle.argtypes=[W.HANDLE]
K.GetProcessTimes.argtypes=[W.HANDLE,C.POINTER(FT),C.POINTER(FT),C.POINTER(FT),C.POINTER(FT)];K.GetExitCodeProcess.argtypes=[W.HANDLE,C.POINTER(W.DWORD)]
P.GetProcessMemoryInfo.argtypes=[W.HANDLE,C.POINTER(MEM),W.DWORD]
def processes():
 h=K.CreateToolhelp32Snapshot(2,0);v=PE();v.size=C.sizeof(v);out=[]
 ok=K.Process32FirstW(h,C.byref(v))
 while ok:
  out.append((v.pid,v.parent,v.name));ok=K.Process32NextW(h,C.byref(v))
 K.CloseHandle(h);return out
def seconds(x):return ((x.high<<32)+x.low)/1e7-11644473600
def wait(p,timeout,path):
 deadline=time.monotonic()+timeout;known={p.pid};tracked={};finished=[]
 while True:
  snapshot=processes();change=True
  while change:
   change=False
   for pid,parent,name in snapshot:
    if parent in known and pid not in known:
     known.add(pid);h=K.OpenProcess(0x0400|0x0010,False,pid)
     if h:tracked[pid]=(h,{'pid':pid,'parent_pid':parent,'name':name,'first_seen_monotonic':time.monotonic()})
     change=True
  for pid,(h,row) in list(tracked.items()):
   code=W.DWORD();K.GetExitCodeProcess(h,C.byref(code))
   a,b,c,d=FT(),FT(),FT(),FT();K.GetProcessTimes(h,C.byref(a),C.byref(b),C.byref(c),C.byref(d))
   m=MEM();m.cb=C.sizeof(m);P.GetProcessMemoryInfo(h,C.byref(m),C.sizeof(m))
   row['peak_rss_bytes']=max(row.get('peak_rss_bytes',0),m.peak)
   row['os_start_epoch']=seconds(a)
   if code.value!=259:
    row.update(os_end_epoch=seconds(b),exit_code=code.value,observed_monotonic_end=time.monotonic());row['os_wall_seconds']=row['os_end_epoch']-row['os_start_epoch']
    finished.append(row);K.CloseHandle(h);del tracked[pid]
  if p.poll() is not None and not tracked:break
  if time.monotonic()>deadline:raise TimeoutError('journey deadline')
  time.sleep(.1)
 path.write_text(json.dumps(sorted(finished,key=lambda r:r['os_start_epoch']),indent=2),encoding='utf8')
 return p.returncode
