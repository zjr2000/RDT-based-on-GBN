from rdt import RDTSocket


client = RDTSocket()
client.bind(('127.0.0.1', 0))
client.connect(('127.0.0.1', 12356))
client.send(b'test1234567890abcdefghijklmnopqrstuvwxyz')
print('Receive:', client.recv(1024))
client.close()
