from rdt import RDTSocket

server = RDTSocket()
server.bind(('127.0.0.1', 12356))
conn, _ = server.accept()
msg = conn.recv(1024)
print('Receive:', msg)
conn.send(msg)
conn.close()
