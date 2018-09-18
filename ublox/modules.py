import serial
import binascii
from collections import namedtuple
import logging


logger = logging.getLogger(__name__)

AT_REBOOT = 'AT+NRB'
AT_CONNECT = 'AT+CSCON=1'
AT_ENABLE_NETWORK_REGISTRATION = 'AT+CEREG=1'
AT_ENABLE_POWER_SAVING_MODE = 'AT+NPSMR=1'
AT_ENABLE_ALL_FUNCTIONS = 'AT+CFUN=1'
AT_CONNECT_TO_TELIA = 'AT+COPS=1,2,"24001"'
AT_CONNECT_TO_3 = 'AT+COPS=1,2,"24002"'
AT_GET_IP = 'AT+CGPADDR'

AT_SEND_TO = 'AT+NSOST=0'
AT_CHECK_CONNECTION_STATUS = 'AT+CSCON?'
AT_RADIO_INFORMATION = 'AT+NUESTATS="RADIO"'


Stats = namedtuple('Stats', 'type name value')

# TODO: Make communication with the module in a separate thread. Using a queue
# for communication of AT commands and implement a state-machine for handling
# AT-commands. Also always keep reading thte serial line for URCs

# TODO: Make a socket interface
# TODO: Handle ERROR messages.


class SaraN211Module:
    BAUDRATE = 9600
    RTSCTS = False

    def __init__(self, serial_port: str, echo=False):
        self._serial_port = serial_port
        self._serial = serial.Serial(self._serial_port,
                                     baudrate=self.BAUDRATE,
                                     rtscts=self.RTSCTS,
                                     timeout=300)
        self.echo = echo
        self.ip = None
        # TODO: Maybe impelemtn property that would issue AT commands?
        self.connected = False
        self.available_messages = list()
        # TODO: make a class containing all states
        self.eps_reg_status = None
        self.radio_signal_power = None
        self.radio_total_power = None
        self.radio_tx_power = None
        self.radio_tx_time = None
        self.radio_rx_time = None
        self.radio_cell_id = None
        self.radio_ecl = None
        self.radio_snr = None
        self.radio_earfcn = None
        self.radio_pci = None
        self.radio_rsrq = None

    def reboot(self):
        """Rebooting the module"""
        logger.debug(f'Initiating reboot of module')
        self._at_action(AT_REBOOT)

    def init(self):
        """Running all commands to get the module up an working"""

        logger.info(f'Starting initiation process')
        self._at_action(AT_CONNECT)
        self._at_action(AT_ENABLE_NETWORK_REGISTRATION)
        self._at_action(AT_ENABLE_POWER_SAVING_MODE)
        self._at_action(AT_ENABLE_ALL_FUNCTIONS)
        logger.info(f'Finished initiation process')

    def connect(self, operator='telia'):
        """Will initiate commands to connect to operators network and wait until
        connected."""
        logger.info(f'Trying to connect to operator {operator} network')
        # TODO: Handle connection independent of home network or roaming.
        if operator == 'telia':
            self._at_action(AT_CONNECT_TO_TELIA)
            self._read_line_until_contains('CEREG: 5')
        elif operator == '3' or operator == 'tre':
            self._at_action(AT_CONNECT_TO_3)
            self._read_line_until_contains('CEREG: 1')
        else:
            raise ValueError(f'Operator {operator} is not supported')

        logger.info(f'Connected to {operator}')
        self._at_action(AT_GET_IP)
        self._update_radio_statistics()

    def create_socket(self, port: int):
        """Creates a socket that can be used to send and recieve data"""
        logger.info(f'Creating socket on port {port}')
        AT_CREATE_SOCKET = f'AT+NSOCR="DGRAM",17,{port}'
        socket_id = self._at_action(AT_CREATE_SOCKET)
        logger.info(f'Socket created with id: {socket_id}')

    def send_udp_data(self, host: str, port: int, data: str):
        """Send a UDP message"""
        logger.info(f'Sending UDP message to {host}:{port}  :  {data}')
        _data = binascii.hexlify(data.encode()).upper().decode()
        length = len(data)
        atc = f'{AT_SEND_TO},"{host}",{port},{length},"{_data}"'
        result = self._at_action(atc)
        return result

    def receive_udp_data(self):
        """Recieve a UDP message"""
        # TODO: Do getting of data and parsing in callback on URC.
        logger.info(f'Waiting for UDP message')
        self._read_line_until_contains('+NSONMI')
        message_info = self.available_messages.pop(0)
        message = self._at_action(f'AT+NSORF={message_info.decode()}')
        response = self._parse_udp_response(message[0])
        logger.info(f'Recieved UDP message: {response}')
        return response

    def _at_action(self, at_command):
        """
        Small wrapper to issue a AT command. Will wait for the Module to return
        OK.
        """
        logger.debug(f'Applying AT Command: {at_command}')
        self._write(at_command)
        irc = self._read_line_until_contains('OK')
        logger.debug(f'AT Command response = {irc}')
        return irc

    def _write(self, data):
        """
        Writing data to the module is simple. But it needs to end with \r\n
        to accept the command. The module will answer with an empty lime as
        acknowledgement
        """
        data_to_send = data
        if isinstance(data, str):  # if someone sent in a string make it bytes
            data_to_send = data.encode()

        if not data_to_send.endswith(b'\r\n'):
            # someone didnt add the CR an LN so we need to send it
            data_to_send += b'\r\n'

        self._serial.write(data_to_send)

        logger.debug(f'Sent: {data_to_send}')
        ack = self._serial.readline()

        if self.echo:
            # when echo is on we will have recieved the message we sent and
            # will get it in the ack response read. But it will not send \n.
            # so we can omitt the data we send + i char for the \r
            # TODO: check that the data we recieved acctually is data + \r
            ack = ack[(len(data)+1):]

        if ack != b'\r\n':
            raise ValueError(f'Ack was not received properly, received {ack}')

    @staticmethod
    def _remove_line_ending(line: bytes):
        """
        To not have to deal with line endings in the data we can used this to
        remove them.
        """
        if line.endswith(b'\r\n'):
            return line[:-2]
        else:
            return line

    def _read_line_until_contains(self, slice):
        """
        Simmillar to read_until, but will read whole lines so we can use proper
        timeout management. Any URC:s that is read will be handled and we will
        return the IRC:s collected.
        """
        _slice = slice
        if isinstance(slice, str):
            _slice = slice.encode()

        data_list = list()
        irc_list = list()

        while True:
            line = self._remove_line_ending(self._serial.readline())

            if line.startswith(b'+'):
                self._process_urc(line)
            elif line == b'OK':
                pass

            elif line == b'':
                pass

            else:
                irc_list.append(line)  # the can only be an IRC

            if _slice in line:
                data_list.append(line)
                break
            else:
                data_list.append(line)

        clean_list = [response for response in data_list if not response == b'']

        logger.debug(f'Received: {clean_list}')

        return irc_list

    @staticmethod
    def _parse_udp_response(message: bytes):
        _message = message.replace(b'"', b'')
        socket, ip, port, length, _data, remaining_bytes = _message.split(b',')
        data = bytes.fromhex(_data.decode())
        return data

    def _process_urc(self, urc: bytes):
        """
        URC = unsolicited result code
        When waiting on answer from the module it is possible that the module
        sends urcs via +commands. So after the urcs are
        collected we run this method to process them.

        """

        callbackmap = {'CSCON': self._update_connection_status_callback,
                       'CEREG': self._update_eps_reg_status_callback,
                       'CGPADDR': self._update_ip_address_callback,
                       'NSONMI': self._add_available_message_callback}

        _urc = urc.decode()
        logger.debug(f'Processing URC: {_urc}')
        urc_id = _urc[1:_urc.find(':')]
        callback = callbackmap.get(urc_id, None)
        if callback:
            callback(urc)
        else:
            logger.debug(f'Unhandled urc: {urc}')

    def _add_available_message_callback(self, urc: bytes):
        _urc, data = urc.split(b':')
        result = data.lstrip()
        logger.debug(f'Recieved data: {result}')
        self.available_messages.append(result)

    def _update_radio_statistics(self):
        radio_data = self._at_action(AT_RADIO_INFORMATION)
        self._parse_radio_stats(radio_data)

    def _update_connection_status_callback(self, urc):
        """
        In the AT urc +CSCON: 1 the last char is indication if the
        connection is idle or connected

        """
        status = bool(int(urc[-1]))
        self.connected = status
        logger.info(f'Changed the connection status to {status}')

    def _update_eps_reg_status_callback(self, urc):
        """
        The command could return more than just the status.
        Maybe a regex would be good
        But for now we just check the last as int
        """
        status = int(urc[-1])
        self.eps_reg_status = status
        logger.info(f'Updated status EPS Registration = {status}')

    def _update_ip_address_callback(self, urc: bytes):
        """
        Update the IP Address of the module
        """
        # TODO: this is per socket. Need to implement socket handling
        _urc = urc.decode()
        ip_addr = _urc[(_urc.find('"') + 1):-1]
        self.ip = ip_addr
        logger.info(f'Updated the IP Address of the module to {ip_addr}')

    def _parse_radio_stats(self, irc_buffer):

        stats = [self._parse_radio_stats_string(item) for item in irc_buffer]

        for stat in stats:
            if not stat:
                continue
            if stat.type == 'RADIO' and stat.name == 'Signal power':
                self.radio_signal_power = stat.value
            elif stat.type == 'RADIO' and stat.name == 'Total power':
                self.radio_total_power = stat.value
            elif stat.type == 'RADIO' and stat.name == 'TX power':
                self.radio_tx_power = stat.value
            elif stat.type == 'RADIO' and stat.name == 'TX time':
                self.radio_tx_time = stat.value
            elif stat.type == 'RADIO' and stat.name == 'RX time':
                self.radio_rx_time = stat.value
            elif stat.type == 'RADIO' and stat.name == 'Cell ID':
                self.radio_cell_id = stat.value
            elif stat.type == 'RADIO' and stat.name == 'ECL':
                self.radio_ecl = stat.value
            elif stat.type == 'RADIO' and stat.name == 'SNR':
                self.radio_snr = stat.value
            elif stat.type == 'RADIO' and stat.name == 'EARFCN':
                self.radio_earfcn = stat.value
            elif stat.type == 'RADIO' and stat.name == 'PCI':
                self.radio_pci = stat.value
            elif stat.type == 'RADIO' and stat.name == 'RSRQ':
                self.radio_rsrq = stat.value
            else:
                logger.debug(f'Unhandled statistics data: {stat}')

    @staticmethod
    def _parse_radio_stats_string(stats_byte_string: bytes):
        """
        The string is like: b'NUESTATS: "RADIO","Signal power",-682'
        :param stats_byte_string:
        :return: NamedTuple Stats
        """
        parts = stats_byte_string.decode().split(':')

        irc: str = parts[0].strip()
        data: str = parts[1].strip().replace('"', '')

        data_parts = data.split(',')
        if irc == 'NUESTATS':
            return Stats(data_parts[0], data_parts[1], int(data_parts[2]))
        else:
            return None

    def __repr__(self):
        return f'NBIoTModule(serial_port="{self._serial_port}")'


class SaraR4Module(SaraN211Module):
    BAUDRATE = 115200
    RTSCTS = 1

    AT_CREATE_SOCKET = 'AT+USORC=17'

    def init(self):
        #self._at_action('ATE0')
        self._at_action('AT+CFUN=15')  # Enable radio funtions
        self._at_action('AT+CMEE=2')  # enable verbose errors
        self._at_action('AT+CEREG=3')  # needed? or can it be just =1?
        self.set_mode()
        self.set_pdp_context()

    #def create_socket(self, port: int):
    #    self._at_action(self.AT_CREATE_SOCKET)

    def set_mode(self, mode='nb1'):

        mode_dict = {'nb1': 'AT+URAT=8',
                     'lte-m': 'AT+URAT=7'}

        response = self._at_action(mode_dict[mode])
        logger.info(f'Radio Mode set to {mode}')

    def set_pdp_context(self):
        self._at_action('AT+CGDCONT=1,"IP","internet.ts.m2m"')

    def create_socket(self, port: int = None):
        action = f'AT+USOCR=17'

        if port:
            action += f',{port}'
        self._at_action(action)

    def send_udp_data(self, host: str, port: int, data: str):
        """Send a UDP message"""
        logger.info(f'Sending UDP message to {host}:{port}  :  {data}')
        _data = binascii.hexlify(data.encode()).upper().decode()
        #_data = data
        length = len(data)
        atc = f'AT+USOST=0,"{host}",{port},{length},"{_data}"'
        result = self._at_action(atc)
        return result


