import threading
from USocket import UnreliableSocket
from queue import Queue
from threading import Thread
from enum import Enum, auto
from packet import packet
from timer import Timer
import time


class RDTSocket(UnreliableSocket):
    MSS = 1024  # Max segment size
    CWND = 1024*5  # unit: bytes
    # TODO             Congestion control
    """
    The functions with which you are to build your RDT.
    -   recvfrom(bufsize)->bytes, addr
    -   sendto(bytes, address)
    -   bind(address)

    You can set the mode of the socket.
    -   settimeout(timeout)
    -   setblocking(flag)
    By default, a socket is created in the blocking mode. 
    https://docs.python.org/3/library/socket.html#socket-timeouts

    """

    def __init__(self, rate=None, debug=True):
        super().__init__(rate=rate)
        self._rate = rate
        self._send_to = None
        self._recv_from = None
        self.debug = debug
        self.conn = None
        self.thread_lock = threading.Lock()

    def accept(self):
        """
        Accept a connection. The socket must be bound to an address and listening for
        connections. The return value is a pair (conn, address) where conn is a new
        socket object usable to send and receive data on the connection, and address
        is the address bound to the socket on the other end of the connection.

        This function should be blocking.
        """
        msg = None
        addr = None
        while True:
            msg, addr = self.recvfrom(2048)
            if msg is None:
                continue
            pkt = packet(pkt=msg)
            if not pkt.corrupted and pkt.syn == 1:
                break
        if self.debug:
            print("Receive syn, client addr =", addr)
        new_socket = RDTSocket(rate=self._rate)
        new_socket.bind(('127.0.0.1', 0))
        self.thread_lock.acquire()
        new_socket.conn = Connection(as_server=True, socket=new_socket, dst_addr=addr, state=State.SYN_RCVD)

        while new_socket.conn.state == State.SYN_RCVD:
            pass
        if self.debug:
            print('Connection established!')
        self.thread_lock.release()
        new_socket.set_send_to(new_socket.send)
        new_socket.set_recv_from(new_socket.recv)
        return new_socket, None

    def connect(self, address: (str, int)):
        """
        Connect to a remote socket at address.
        Corresponds to the process of establishing a connection on the client side.
        """
        # self.thread_lock.acquire()
        msg = None
        addr = None
        while True:
            self.sendto(packet(syn=1).make_pkt(), address)
            self.settimeout(3)
            try:
                msg, addr = self.recvfrom(2048)
            except:
                continue
            if msg is None or addr[0] != address[0]:
                continue
            pkt = packet(pkt=msg)
            if not pkt.corrupted and pkt.syn == 1 and pkt.ack == 1:
                break
        if self.debug:
            print('Receive syn_ack, server address =', addr)
        self.conn = Connection(as_server=False, socket=self, dst_addr=addr, state=State.ESTABLISHED)
        # self.thread_lock.release()

        if self.debug:
            print("Connect successfully!")
        self.set_send_to(self.send)
        self.set_recv_from(self.recv)

    def recv(self, bufsize: int) -> bytes:
        """
        Receive data from the socket.
        The return value is a bytes object representing the data received.
        The maximum amount of data to be received at once is specified by bufsize.

        Note that ONLY data send by the peer should be accepted.
        In other words, if someone else sends data to you from another address,
        it MUST NOT affect the data returned by this function.
        """
        assert self._recv_from, "Connection not established yet. Use recvfrom instead."
        assert self.conn.state != State.CLOSED, "Connection not established yet"
        if self.debug:
            print('Waiting message')
        return self.conn.recv(bufsize)

    def send(self, msg: bytes):
        """
        Send data to the socket.
        The socket must be connected to a remote socket, i.e. self._send_to must not be none.
        """
        assert self._send_to, "Connection not established yet. Use sendto instead."
        assert self.conn.state != State.CLOSED, "Connection not established yet"
        self.conn.send(msg)

    def close(self):
        """
        Finish the connection and release resources. For simplicity, assume that
        after a socket is closed, neither futher sends nor receives are allowed.
        """
        self.conn.wait_close = True
        # 等待内部关闭
        while self.conn.state != State.CLOSED:
            pass
        super().close()

    def set_send_to(self, send_to):
        self._send_to = send_to

    def set_recv_from(self, recv_from):
        self._recv_from = recv_from


class State(Enum):
    # for server: SYN_SENT, FIN_WAIT1, FIN_WAIT2, TIME_WAIT
    # for client: SYN_RCVD, CLOSE_WAIT, LAST_ACK, CLOSED
    CLOSED = auto()
    LISTEN = auto()
    SYN_SENT = auto()
    SYN_RCVD = auto()
    ESTABLISHED = auto()
    LAST_ACK = auto()
    TIME_WAIT = auto()
    FIN_WAIT1 = auto()
    FIN_WAIT2 = auto()
    CLOSE_WAIT = auto()


class StateMachine(Thread):
    def __init__(self, conn):
        Thread.__init__(self)
        self.connection: Connection = conn
        self.send_timer = Timer(3.5)
        self.state_timer = Timer(3)
        self.start_conn = False
        self.alive = True

    def run(self):
        conn: Connection = self.connection
        no_packet = 0
        sever_resend_fin_cnt = 0
        # conn.socket.thread_lock.acquire()

        if conn.as_server:
            self.state_timer.start_timer()

        while self.alive:
            if conn.state in [State.ESTABLISHED, State.CLOSE_WAIT]:
                # slide window (Remove packet already be acked)
                for pkt in conn.send_window:
                    if pkt.seq_num < conn.base_seq_num:
                        conn.send_window.remove(pkt)
                # time out, resend packet in window
                if self.send_timer.is_time_out():
                    self.send_timer.start_timer()
                    for pkt in conn.send_window:
                        if conn.socket.debug:
                            print(conn.state, 'Resend packet seq_num =', pkt.seq_num)
                        conn.send_unchecked_packet(pkt)
                # maintain window
                while conn.send_queue.qsize() != 0 \
                        and conn.next_seq_num < conn.base_seq_num + RDTSocket.CWND:
                    data = conn.send_queue.get()
                    to_send = packet(payload=data, seq_num=conn.next_seq_num, ack=1)
                    if conn.socket.debug:
                        print(conn.state, 'Send packet seq_num =', to_send.seq_num)
                    conn.send_packet(to_send)
                    if conn.base_seq_num == conn.next_seq_num:
                        self.send_timer.start_timer()
                    conn.next_seq_num += to_send.pkt_len

            # Client waiting for close
            if conn.state == State.TIME_WAIT:
                if no_packet >= 6:
                    if conn.socket.debug:
                        print('Close connection')
                    conn.close()
                    conn.state = State.CLOSED
                    break
            # Server send finish
            elif conn.state == State.CLOSE_WAIT:
                if conn.wait_close and conn.send_queue.qsize() == 0 and len(conn.send_window) == 0:
                    if conn.socket.debug:
                        print(conn.state, 'Finish sending, send fin, change state to LAST_ACK')
                    to_send = packet(fin=1)
                    conn.send_unchecked_packet(to_send)
                    conn.state = State.LAST_ACK
                    self.state_timer.start_timer()
            # Client send finish
            elif conn.state == State.ESTABLISHED and not conn.as_server:
                if conn.wait_close and conn.send_queue.qsize() == 0 and len(conn.send_window) == 0:
                    if conn.socket.debug:
                        print(conn.state, 'Finish sending. FIN sent. Move to FIN_WAIT1')
                    conn.state = State.FIN_WAIT1
                    to_send = packet(fin=1)
                    conn.send_unchecked_packet(to_send)
                    self.state_timer.start_timer()
            # Server resend syn_ack
            elif conn.state == State.SYN_RCVD:
                if self.state_timer.is_time_out():
                    if conn.socket.debug:
                        print(conn.state, 'time out! Resend syn_ack')
                    conn.send_unchecked_packet(packet(syn=1, ack=1))
                    self.state_timer.start_timer()
            # Client resend fin
            elif conn.state == State.FIN_WAIT1:
                if self.state_timer.is_time_out():
                    if conn.socket.debug:
                        print(conn.state, 'time out! Resend fin')
                    conn.send_unchecked_packet(packet(fin=1))
                    self.state_timer.start_timer()
            # Server resend fin or close
            elif conn.state == State.LAST_ACK:
                if self.state_timer.is_time_out():
                    if conn.socket.debug:
                        print(conn.state, 'time out! Resend fin')
                    conn.send_unchecked_packet(packet(fin=1))
                    sever_resend_fin_cnt += 1
                    self.state_timer.start_timer()
                if sever_resend_fin_cnt > 3:
                    if conn.socket.debug:
                        print(conn.state, 'Resend fin three times! Close directly!')
                    conn.close()
                    conn.state = State.CLOSED
                    self.state_timer.stop_timer()

            pkt: packet
            try:
                pkt = conn.receive.get(timeout=0.5)
                no_packet = 0
            except:
                no_packet += 1
                # print('no_packet_cnt:', no_packet)
                continue
            # if conn.socket.debug:
            #     print('syn=', pkt.syn, ' ack=', pkt.ack, ' fin=', pkt.fin, ' seq_num=', pkt.seq_num, ' ack_num=',
            #           pkt.ack_num,
            #           'payload_length = ', pkt.pkt_len)
            # receive ack packet
            if pkt.pkt_len == 0:
                # cumulative ack
                conn.base_seq_num = max(pkt.ack_num, conn.base_seq_num)
                if conn.base_seq_num == conn.next_seq_num:
                    self.send_timer.stop_timer()
                else:
                    self.send_timer.start_timer()
            # receive data packet
            else:
                # receive expected packet
                if pkt.seq_num == conn.expected_seq_num:
                    if conn.socket.debug:
                        print('Receive right packet, seq_num =', pkt.seq_num)
                    for i in pkt.payload:
                        conn.message.put(i.to_bytes(length=1, byteorder='little'))
                    conn.expected_seq_num += pkt.pkt_len
                else:
                    if conn.socket.debug:
                        print('Receive wrong packet, seq_num =', pkt.seq_num)
                conn.send_unchecked_packet(packet(ack_num=conn.expected_seq_num))

            # Server waiting for ack, which belong to connection establish
            if conn.state == State.SYN_RCVD:
                if pkt.ack:
                    if conn.socket.debug:
                        print('Recieve ack, change state to ESTABLISHED')
                    conn.state = State.ESTABLISHED
                    self.state_timer.stop_timer()
            # Server receive fin
            elif conn.state in [State.ESTABLISHED, State.CLOSE_WAIT, State.LAST_ACK] and conn.as_server:
                if pkt.fin:
                    if conn.socket.debug:
                        print(conn.state, 'Receive FIN, send fin_ack back!')
                    to_send = packet(fin=1, ack=1)
                    conn.send_unchecked_packet(to_send)
                    if conn.state == State.ESTABLISHED:
                        conn.state = State.CLOSE_WAIT
            # Server waiting for fin_ack
            elif conn.state == State.LAST_ACK:
                if pkt.ack and pkt.fin:
                    if conn.socket.debug:
                        print(conn.state, 'Receive fin_ack, close connection')
                    conn.close()
                    conn.state = State.CLOSED
                    self.state_timer.stop_timer()
                    break

            elif conn.state == State.FIN_WAIT1:
                if pkt.ack and pkt.fin:
                    if conn.socket.debug:
                        print(conn.state, 'Receive fin_ack, change state to FIN_WAIT2')
                    conn.state = State.FIN_WAIT2
                    self.state_timer.stop_timer()

            elif conn.state == State.FIN_WAIT2:
                if pkt.fin:
                    if conn.socket.debug:
                        print(conn.state, 'Receive fin, send fin_ack back')
                    to_send = packet(fin=1, ack=1)
                    conn.send_unchecked_packet(to_send)
                    conn.state = State.TIME_WAIT

        # conn.socket.thread_lock.release()


class Connection:
    def __init__(self, as_server, socket: RDTSocket, dst_addr, state):
        super().__init__()
        self.wait_close = False
        self.as_server = as_server
        self.socket = socket
        # GBN variables
        self.base_seq_num = 0
        self.next_seq_num = 0
        self.expected_seq_num = 0
        # receieve buffer
        self.receive: Queue[packet] = Queue()
        # message buffer
        self.message: Queue[bytes] = Queue()
        # send buffer
        self.send_queue: Queue[bytes] = Queue()
        # send window: already sent, but not yet received
        self.send_window = list()
        self.state = state
        self.recv_state = True
        self.dst_addr = dst_addr
        # Start state machine
        self.machine = StateMachine(self)
        self.machine.start()
        # Start receive thread
        self.receive_thread = Thread(target=self.recv_msg_to_buffer)
        self.receive_thread.start()
        # server need to send syn_ack first
        if as_server:
            self.send_unchecked_packet(packet(syn=1, ack=1))

    def send(self, message: bytes):
        chunks = [message[i:min(len(message), i + RDTSocket.MSS)]
                  for i in range(0, len(message), RDTSocket.MSS)]
        for c in chunks:
            self.send_queue.put(c)
        if self.socket.debug:
            print('push', len(message), 'bytes')

    def send_unchecked_packet(self, pkt: packet):
        self.socket.sendto(pkt.make_pkt(), self.dst_addr)

    def send_packet(self, pkt: packet):
        self.send_window.append(pkt)
        self.socket.sendto(pkt.make_pkt(), self.dst_addr)

    def receive_packet(self, pkt: packet):
        self.receive.put(pkt)

    def recv(self, bufsize):
        # geting message until buffer is not empty
        while self.message.qsize() == 0:
            pass

        final_message = b''
        i = 0
        while self.message.qsize() != 0 and i < bufsize:
            final_message += self.message.get()
            i += 1
        # try to get more
        while i < bufsize:
            try:
                temp = self.message.get(timeout=5)
                final_message += temp
                i += 1
            except:
                break
        return final_message

    def close(self):
        self.recv_state = False
        self.machine.alive = False

    def recv_msg_to_buffer(self):
        while self.recv_state:
            self.socket.settimeout(1)
            try:
                data, addr = self.socket.recvfrom(100*1024)
            except:
                continue
            if data is None or addr[0] != self.dst_addr[0]:
                continue
            pkt = packet(pkt=data)
            if not pkt.corrupted:
                self.receive_packet(pkt=pkt)
