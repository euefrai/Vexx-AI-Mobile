"""A Windows Job Object owns only project children started suspended by Vexx PC."""
import os
import threading


def windows_listener_pids(port):
    """Read the OS-filtered listener table; some Windows builds misreport dwState.

    TCP_TABLE_OWNER_PID_LISTENER (3) supplies listener semantics independently
    of the row state. Callers must still match their Job Object and probe TCP.
    """
    import ctypes as c
    import socket
    from ctypes import wintypes as w
    api=c.WinDLL('iphlpapi',use_last_error=True).GetExtendedTcpTable
    api.argtypes=[c.c_void_p,c.POINTER(w.DWORD),w.BOOL,w.ULONG,c.c_int,w.ULONG];api.restype=w.DWORD
    owners=set()
    for family,row_size,port_offset,pid_offset in ((socket.AF_INET,24,8,20),(socket.AF_INET6,56,20,52)):
        size=w.DWORD(0)
        result=api(None,c.byref(size),False,family,3,0)
        for _ in range(3):
            if result not in (0,122) or not 4<=size.value<=16*1024*1024:break
            buffer=c.create_string_buffer(size.value)
            result=api(buffer,c.byref(size),False,family,3,0)
            if result==122:continue
            if result:break
            count=c.c_uint32.from_buffer(buffer).value
            if 4+count*row_size>len(buffer):break
            for index in range(count):
                offset=4+index*row_size
                raw=c.c_uint32.from_buffer(buffer,offset+port_offset).value
                if socket.ntohs(raw & 0xffff)==port:
                    owners.add(c.c_uint32.from_buffer(buffer,offset+pid_offset).value)
            break
    return owners


class ProcessGroup:
    def __init__(self):
        self.guard=threading.RLock();self.handle=None;self.closed=False
        if os.name!='nt':return
        import ctypes
        from ctypes import wintypes as w
        self.ctypes=ctypes
        class Basic(ctypes.Structure):
            _fields_=[('process_time',ctypes.c_int64),('job_time',ctypes.c_int64),('flags',w.DWORD),
                      ('min_working',ctypes.c_size_t),('max_working',ctypes.c_size_t),('active',w.DWORD),
                      ('affinity',ctypes.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class IO(ctypes.Structure):
            _fields_=[(name,ctypes.c_uint64) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(ctypes.Structure):
            _fields_=[('basic',Basic),('io',IO),('process_memory',ctypes.c_size_t),('job_memory',ctypes.c_size_t),
                      ('peak_process',ctypes.c_size_t),('peak_job',ctypes.c_size_t)]
        kernel=ctypes.WinDLL('kernel32',use_last_error=True);self.kernel=kernel
        kernel.CreateJobObjectW.argtypes=[ctypes.c_void_p,w.LPCWSTR];kernel.CreateJobObjectW.restype=w.HANDLE
        kernel.SetInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD];kernel.SetInformationJobObject.restype=w.BOOL
        kernel.OpenProcess.argtypes=[w.DWORD,w.BOOL,w.DWORD];kernel.OpenProcess.restype=w.HANDLE
        kernel.AssignProcessToJobObject.argtypes=[w.HANDLE,w.HANDLE];kernel.AssignProcessToJobObject.restype=w.BOOL
        kernel.TerminateJobObject.argtypes=[w.HANDLE,w.UINT];kernel.TerminateJobObject.restype=w.BOOL
        kernel.QueryInformationJobObject.argtypes=[w.HANDLE,ctypes.c_int,ctypes.c_void_p,w.DWORD,ctypes.POINTER(w.DWORD)];kernel.QueryInformationJobObject.restype=w.BOOL
        kernel.CloseHandle.argtypes=[w.HANDLE]
        handle=kernel.CreateJobObjectW(None,None)
        if not handle:raise ctypes.WinError(ctypes.get_last_error())
        info=Extended();info.basic.flags=0x2000|0x8;info.basic.active=128
        if not kernel.SetInformationJobObject(handle,9,ctypes.byref(info),ctypes.sizeof(info)):
            kernel.CloseHandle(handle);raise ctypes.WinError(ctypes.get_last_error())
        self.handle=handle

    def attach(self,pid):
        with self.guard:
            if self.closed:raise ValueError('O grupo de processos já foi encerrado.')
            if os.name!='nt':return
            process=self.kernel.OpenProcess(0x0100|0x0001|0x0400,False,pid)
            if not process:raise self.ctypes.WinError(self.ctypes.get_last_error())
            try:
                if not self.kernel.AssignProcessToJobObject(self.handle,process):
                    raise ValueError('O Windows não permitiu criar um grupo controlado para este projeto.')
            finally:self.kernel.CloseHandle(process)

    def pids(self):
        with self.guard:
            if not self.handle:return []
            c=self.ctypes;buffer=c.create_string_buffer(8+256*c.sizeof(c.c_size_t))
            if not self.kernel.QueryInformationJobObject(self.handle,3,buffer,len(buffer),None):return []
            count=c.c_uint32.from_buffer(buffer,4).value
            return [c.c_size_t.from_buffer(buffer,8+i*c.sizeof(c.c_size_t)).value for i in range(min(count,256))]

    def close(self):
        with self.guard:
            self.closed=True
            if self.handle:
                self.kernel.TerminateJobObject(self.handle,1)
                self.kernel.CloseHandle(self.handle);self.handle=None
