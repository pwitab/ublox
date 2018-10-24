import random


class UbloxSocket:

    def __init__(self, socket_id, module, source_port=None):
        self.socket_id = socket_id
        self.module = module
        self.source_port = source_port or random.randrange(100, 65534, 1)

    def sendto(self, bytes, address):
        pass

    def recvfrom(self, bufsize):
        pass

    def close(self):
        self.module.close_socket(self.socket_id)



class UDPSocket(UbloxSocket):

    def sendto(self, bytes, address):
        self.module.send_udp_data(host=address[0], port=address[1],
                                  data=bytes.decode())
