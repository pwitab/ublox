import time
import binascii


class UbloxSocket:

    def __init__(self, socket_id, module, source_port=None):
        self.socket_id = socket_id
        self.module = module
        self.source_port = source_port

        # When setting a socket to listening this is set to true.
        # But when receiving on the same socket that you sent on you need to
        # send at least once on the socket before you can receive.
        self.able_to_receive = False

    def sendto(self, bytes, address):
        pass

    def recvfrom(self, bufsize):
        pass

    def bind(self, address):
        pass

    def close(self):
        self.module.close_socket(self.socket_id)


class UDPSocket(UbloxSocket):

    def sendto(self, bytes, address):
        self.module.send_udp_data(socket=self.socket_id, host=address[0],
                                  port=address[1], data=bytes.decode())
        self.able_to_receive = True

    def bind(self, address):
        host, port = address
        # Since we can only have the ip of the module we dont care about the
        # hostvalue provided.
        self.module.set_listening_socket(socket=self.socket_id, port=port)
        self.able_to_receive = True

    def recvfrom(self, bufsize):
        """
        As of now there seems to be a problem with URC so there is no
        notification on data received. We continously poll the socket with a
        small delay for not to block the module compleatly until we get a
        result.
        """
        if not self.able_to_receive:
            raise IOError('The ublox socket cannot receive data yet. Either '
                          'set the socket to listening via .bind() or write '
                          'once on the socket.')

        result = self.module.read_udp_data(socket=self.socket_id, length=bufsize)
        ip, port, length, hex_data = result
        address = (ip.decode(), int(port))
        data = binascii.unhexlify(hex_data)
        return data, address
