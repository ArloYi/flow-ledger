"""Windows IP Helper API. No shell commands and no traffic capture."""
import ctypes as C
import hashlib
from ctypes import wintypes as W

U32=C.c_uint32
U64=C.c_uint64
class GUID(C.Structure):
    _fields_=[('bytes',C.c_ubyte*16)]
class Row(C.Structure):
    _fields_=[('Luid',U64),('Index',U32),('Guid',GUID),('Alias',C.c_uint16*257),('Description',C.c_uint16*257),('AddressLength',U32),('Address',C.c_ubyte*32),('PermanentAddress',C.c_ubyte*32)] + [(n,U32) for n in ['Mtu','Type','TunnelType','MediaType','PhysicalMediumType','AccessType','DirectionType']] + [('Flags',C.c_ubyte)] + [(n,U32) for n in ['OperStatus','AdminStatus','MediaConnectState']] + [('NetworkGuid',GUID),('ConnectionType',U32)] + [(n,U64) for n in ['TransmitLinkSpeed','ReceiveLinkSpeed','InOctets','InUcastPkts','InNUcastPkts','InDiscards','InErrors','InUnknownProtos','InUcastOctets','InMulticastOctets','InBroadcastOctets','OutOctets','OutUcastPkts','OutNUcastPkts','OutDiscards','OutErrors','OutUcastOctets','OutMulticastOctets','OutBroadcastOctets','OutQLen']]
class Table(C.Structure):
    _fields_=[('count',U32),('rows',Row*1)]
class Route(C.Structure):
    _fields_=[(n,U32) for n in ['dest','mask','policy','next_hop','index','type','proto','age','asn','metric1','metric2','metric3','metric4','metric5']]
class Neighbor(C.Structure):
    _fields_=[('index',U32),('length',U32),('address',C.c_ubyte*8),('ip',U32),('type',U32)]


def physical(row):
    return bool(row.Flags & 1) and not (row.Flags & 2) and row.Type in (6,71) and row.TunnelType == 0


def row_key(row):
    return 'win-' + bytes(row.Guid.bytes).hex()


def identity(row, routes, neighbors):
    defaults=sorted((r for r in routes if r.index==row.Index and r.dest==0 and r.mask==0 and r.next_hop),key=lambda r:r.metric1)
    for route in defaults:
        for neighbor in neighbors:
            if neighbor.index==row.Index and neighbor.ip==route.next_hop and neighbor.type in (3,4) and 0<neighbor.length<=8:
                key=hashlib.sha256((row_key(row)+'|'+bytes(neighbor.address[:neighbor.length]).hex()).encode()).hexdigest()[:16]
                return {'id':key,'name':'网络 '+key[:4].upper()}
    return {'id':'unknown','name':'无法识别的网络'}


def _table(api, name, struct):
    method=getattr(api,name)
    method.argtypes=[C.c_void_p,C.POINTER(U32),W.BOOL];method.restype=U32
    size=U32()
    status=method(None,C.byref(size),False)
    if status in (232,):return []
    if status!=122:raise OSError(status,name)
    for _ in range(3):
        buffer=C.create_string_buffer(size.value)
        status=method(buffer,C.byref(size),False)
        if status==122:continue
        if status==232:return []
        if status:raise OSError(status,name)
        count=U32.from_buffer(buffer).value
        if 4+count*C.sizeof(struct)>len(buffer):raise ValueError('Invalid IP helper table size')
        return [struct.from_buffer_copy(buffer,4+i*C.sizeof(struct)) for i in range(count)]
    raise OSError('Network table changed repeatedly')


def collect():
    api=C.WinDLL('iphlpapi',use_last_error=True)
    api.GetIfTable2.argtypes=[C.POINTER(C.c_void_p)];api.GetIfTable2.restype=U32
    api.FreeMibTable.argtypes=[C.c_void_p]
    pointer=C.c_void_p()
    result=api.GetIfTable2(C.byref(pointer))
    if result:raise OSError(result,'GetIfTable2')
    try:
        table=C.cast(pointer,C.POINTER(Table)).contents
        rows=[Row.from_buffer_copy(C.string_at(pointer.value+Table.rows.offset+i*C.sizeof(Row),C.sizeof(Row))) for i in range(table.count)]
    finally:api.FreeMibTable(pointer)
    rows=[r for r in rows if physical(r)]
    routes=_table(api,'GetIpForwardTable',Route)
    neighbors=_table(api,'GetIpNetTable',Neighbor)
    counters={row_key(r):(r.InOctets,r.OutOctets) for r in rows}
    networks={row_key(r):identity(r,routes,neighbors) for r in rows if r.OperStatus==1}
    return counters,networks
