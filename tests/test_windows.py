import ctypes
import unittest
from windows_networks import Row,Table,Route,Neighbor,identity,physical

class WindowsLayoutTests(unittest.TestCase):
    def test_native_x64_layout(self):
        self.assertEqual(ctypes.sizeof(Row),1352)
        self.assertEqual(Table.rows.offset,8)
        self.assertEqual(Row.InOctets.offset,1208)
        self.assertEqual(Row.OutOctets.offset,1280)
    def test_physical_only(self):
        r=Row();r.Flags=1;r.Type=71
        self.assertTrue(physical(r));r.Flags=3;self.assertFalse(physical(r))
        r.Flags=1;r.Type=131;self.assertFalse(physical(r))
    def test_gateway_changes_never_inherit_identity(self):
        r=Row();r.Index=7;r.Guid.bytes[0]=1
        route=Route();route.index=7;route.next_hop=10
        neighbor=Neighbor();neighbor.index=7;neighbor.ip=10;neighbor.type=3;neighbor.length=6;neighbor.address[0]=2
        home=identity(r,[route],[neighbor])
        self.assertNotEqual(home['id'],'unknown')
        self.assertEqual(identity(r,[],[neighbor])['id'],'unknown')
        neighbor.address[0]=4
        self.assertNotEqual(identity(r,[route],[neighbor])['id'],home['id'])
        neighbor.index=8;self.assertEqual(identity(r,[route],[neighbor])['id'],'unknown')

if __name__=='__main__':unittest.main()
