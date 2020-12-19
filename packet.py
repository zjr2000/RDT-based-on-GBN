"""
packet format

-------------------------------------------------------------
        flags(1byte)     |
-------------------------------------------------------------
SYN  | FIN | ACK | ack_num | seq_num | packet_len   | CHECKSUM
1bit| 1bit | 1bit| 4byte  |  4byte  |   4byte      |  2byte
-------------------------------------------------------------
payload
len
"""


# 最好是把这些变量都变成field 方便修改
# make_packet方法吧这些field都变成一个byte

class packet(object):

    def __init__(self, pkt=None, payload=b'', syn=0, ack=0, fin=0, seq_num=0, ack_num=0,
                 ):
        self.corrupted = False
        if pkt is None:
            self.payload = payload
            self.syn = syn
            self.fin = fin
            self.ack = ack
            self.ack_num = ack_num
            self.seq_num = seq_num
            self.pkt_len = len(payload)
            self.check_sum = 0
            self.corrupted = False
        else:
            if len(pkt) < 13:
                self.corrupted = True
                return
            temp = pkt[0:13] + pkt[15:]
            current_check_sum = packet.get_check_sum(temp)
            flags = int.from_bytes(pkt[0:1], byteorder='little', signed=True)
            self.ack_num = int.from_bytes(pkt[1:5], byteorder='little', signed=True)
            self.seq_num = int.from_bytes(pkt[5:9], byteorder='little', signed=True)
            self.pkt_len = int.from_bytes(pkt[9:13], byteorder='little', signed=True)
            self.check_sum = int.from_bytes(pkt[13:15], byteorder='little', signed=True)
            if self.check_sum != current_check_sum:
                self.corrupted = True
            self.payload = pkt[15:]
            self.fin = flags % 2
            flags = flags // 2
            self.ack = flags % 2
            flags = flags // 2
            self.syn = flags

    def make_pkt(self):
        self.check_sum = 0
        flags = self.fin + (self.ack << 1) + (self.syn << 2)
        pkt = flags.to_bytes(1, byteorder='little', signed=True)
        pkt += self.ack_num.to_bytes(4, byteorder='little', signed=True)
        pkt += self.seq_num.to_bytes(4, byteorder='little', signed=True)
        pkt += self.pkt_len.to_bytes(4, byteorder='little', signed=True)
        temp = pkt + self.payload
        check_sum = self.get_check_sum(temp)
        pkt += check_sum.to_bytes(2, byteorder='little', signed=True)
        pkt += self.payload
        return pkt


    @staticmethod
    def get_check_sum(payload):
        temp = 0
        for byte in payload:
            temp += byte
        temp = -(temp % 256)
        return temp & 0xFF
