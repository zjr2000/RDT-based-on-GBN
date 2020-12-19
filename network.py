from socket import socket, AF_INET, SOCK_DGRAM, inet_aton, inet_ntoa
import random, time
import threading, queue
from socketserver import ThreadingUDPServer
from packet import packet

lock = threading.Lock()


def bytes_to_addr(bytes):
    return inet_ntoa(bytes[:4]), int.from_bytes(bytes[4:8], 'big')


def addr_to_bytes(addr):
    return inet_aton(addr[0]) + addr[1].to_bytes(4, 'big')


def corrupt(data: bytes) -> bytes:
    raw = list(data)
    # for _ in range(0, random.randint(0, 3)):
    for _ in range(0, 3):
        pos = random.randint(0, len(raw) - 1)
        raw[pos] = random.randint(0, 255)
    return bytes(raw)


class Server(ThreadingUDPServer):
    def __init__(self, addr, rate=None, delay=None, corrupt=None):
        super().__init__(addr, None)
        self.rate = rate
        self.buffer = 0
        self.delay = delay
        self.corrupt = corrupt
        self.server_addr = None
        self.client_addr = None

    def verify_request(self, request, client_address):
        if self.buffer < 10:
            self.buffer += 1
            return True
        else:
            return False

    def finish_request(self, request, client_address):
        data, socket = request
        lock.acquire()
        if self.rate: time.sleep(len(data) / self.rate)
        self.buffer -= 1
        lock.release()

        to = bytes_to_addr(data[:8])
        if self.client_addr is None:
            self.client_addr = client_address
            self.server_addr = to

        if self.client_addr == client_address:
            frm_str = 'client'
            to_str = 'server'
        else:
            frm_str = 'server'
            to_str = 'client'
        print('从', frm_str, '发往', to_str)
        temp = data[8:]
        if random.random() < self.corrupt:
            print('Make corrupt pkt!!!')
            temp = corrupt(temp)
        socket.sendto(addr_to_bytes(client_address) + temp, to)
        pkt = packet(pkt=data[8:])
        print('syn=', pkt.syn, ' ack=', pkt.ack, ' fin=', pkt.fin, ' seq_num=', pkt.seq_num, ' ack_num=', pkt.ack_num,
              'payload_length = ', pkt.pkt_len)


server_address = ('127.0.0.1', 12345)

if __name__ == '__main__':
    with Server(addr=server_address, corrupt=0.1, rate=(1024*10)) as server:
        server.serve_forever()