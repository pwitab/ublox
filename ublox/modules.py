import time

import serial
import binascii
from collections import namedtuple
import logging

from ublox.socket import UDPSocket

logger = logging.getLogger(__name__)

Stats = namedtuple('Stats', 'type name value')


# TODO: Make communication with the module in a separate thread. Using a queue
# for communication of AT commands and implement a state-machine for handling
# AT-commands. Also always keep reading thte serial line for URCs

# TODO: Make a socket interface

class CMEError(Exception):
    """CME ERROR on Module"""


class ATError(Exception):
    """AT Command Error"""


class ConnectionTimeoutError(Exception):
    """Module did not connect within the specified time"""


class SaraN211Module:
    BAUDRATE = 9600
    RTSCTS = False

    AT_ENABLE_NETWORK_REGISTRATION = 'AT+CEREG=1'
    AT_ENABLE_SIGNALING_CONNECTION_URC = 'AT+CSCON=1'
    AT_ENABLE_POWER_SAVING_MODE = 'AT+NPSMR=1'
    AT_ENABLE_ALL_RADIO_FUNCTIONS = 'AT+CFUN=1'
    AT_REBOOT = 'AT+NRB'
    AT_CLOSE_SOCKET = 'AT+NSOCL'

    AT_GET_IP = 'AT+CGPADDR'

    AT_SEND_TO = 'AT+NSOST=0'
    AT_CHECK_CONNECTION_STATUS = 'AT+CSCON?'
    AT_RADIO_INFORMATION = 'AT+NUESTATS="RADIO"'

    REBOOT_TIME = 0

    SUPPORTED_SOCKET_TYPES = ['UDP']

    def __init__(self, serial_port: str, roaming=False, echo=False):
        self._serial_port = serial_port
        self._serial = serial.Serial(self._serial_port, baudrate=self.BAUDRATE,
                                     rtscts=self.RTSCTS, timeout=300)
        self.echo = echo
        self.roaming = roaming
        self.ip = None
        self.connected = False
        self.sockets = {}
        self.available_messages = list()
        # TODO: make a class containing all states
        self.registration_status = None
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
        logger.info('Rebooting module')
        self._at_action(self.AT_REBOOT)
        logger.info('waiting for module to boot up')
        time.sleep(self.REBOOT_TIME)
        self._serial.flushInput()  # Flush the serial ports to get rid of crap.
        self._serial.flushOutput()
        logger.info('Module rebooted')

    def setup(self):
        """Running all commands to get the module up an working"""

        logger.info(f'Starting initiation process')
        self.enable_signaling_connection_urc()
        self.enable_network_registration()
        self.enable_psm_mode()
        self.enable_radio_functions()
        logger.info(f'Finished initiation process')

    def enable_psm_mode(self):
        self._at_action(self.AT_ENABLE_POWER_SAVING_MODE)
        logger.info('Enabled Power Save Mode')

    def enable_signaling_connection_urc(self):
        self._at_action(self.AT_ENABLE_SIGNALING_CONNECTION_URC)
        logger.info('Signaling Connection URC enabled')

    def enable_network_registration(self):
        self._at_action(self.AT_ENABLE_NETWORK_REGISTRATION)
        logger.info('Network registration enabled')

    def enable_radio_functions(self):
        self._at_action(self.AT_ENABLE_ALL_RADIO_FUNCTIONS)
        logger.info('All radio functions enabled')

    def connect(self, operator: int, roaming=False):

        """Will initiate commands to connect to operators network and wait until
        connected."""
        logger.info(f'Trying to connect to operator {operator} network')
        # TODO: Handle connection independent of home network or roaming.

        if operator:
            at_command = f'AT+COPS=1,2,"{operator}"'

        else:
            at_command = f'AT+COPS=0'

        self._at_action(at_command)
        self._await_connection(roaming or self.roaming)
        logger.info(f'Connected to {operator}')

    def create_socket(self, socket_type='UDP', port: int = None):
        logger.info(f'Creating {socket_type} socket')

        if socket_type.upper() not in self.SUPPORTED_SOCKET_TYPES:
            raise ValueError(f'Module does not support {socket_type} sockets')

        sock = None
        if socket_type.upper() == 'UDP':
            sock = self._create_upd_socket(port)

        elif socket_type.upper() == 'TCP':
            sock = self._create_tcp_socket(port)

        logger.info(f'{socket_type} socket created')

        self.sockets[sock.socket_id] = sock

        return sock

    def _create_upd_socket(self, port):
        at_command = f'AT+NSOCR="DGRAM",17'
        if port:
            at_command = at_command + f',{port}'

        socket_id = self._at_action(at_command)
        sock = UDPSocket(socket_id, self, port)
        return sock

    def _create_tcp_socket(self, port):
        raise NotImplementedError('Sara211 does not support TCP')

    def close_socket(self, socket_id):
        logger.info(f'Closing socket {socket_id}')
        if socket_id not in self.sockets.keys():
            raise ValueError('Specified socket id does not exist')
        result = self._at_action(f'{self.AT_CLOSE_SOCKET}={socket_id}')
        del self.sockets[socket_id]
        return result

    def send_udp_data(self, host: str, port: int, data: str):
        """Send a UDP message"""
        logger.info(f'Sending UDP message to {host}:{port}  :  {data}')
        _data = binascii.hexlify(data.encode()).upper().decode()
        length = len(data)
        atc = f'{self.AT_SEND_TO},"{host}",{port},{length},"{_data}"'
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

    def _at_action(self, at_command, capture_urc=False):
        """
        Small wrapper to issue a AT command. Will wait for the Module to return
        OK.
        """
        logger.debug(f'Applying AT Command: {at_command}')
        self._write(at_command)
        irc = self._read_line_until_contains('OK', capture_urc=capture_urc)
        if irc is not None:
            logger.debug(f'AT Command response = {irc}')
        return irc

    def _write(self, data):
        """
        Writing data to the module is simple. But it needs to end with \r\n
        to accept the command. The module will answer with an empty line as
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
            ack = ack[(len(data) + 1):]

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

    def _read_line_until_contains(self, slice, capture_urc=False):
        """
        Similar to read_until, but will read whole lines so we can use proper
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
                if capture_urc:
                    irc_list.append(line)  # add the urc as an irc
                else:
                    self._process_urc(line)

            elif line == b'OK':
                pass

            elif line.startswith(b'ERROR'):
                raise ATError('Error on AT Command')

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
                       'NSONMI': self._add_available_message_callback,
                       'CME ERROR': self._handle_cme_error, }

        _urc = urc.decode()
        logger.debug(f'Processing URC: {_urc}')
        urc_id = _urc[1:_urc.find(':')]
        callback = callbackmap.get(urc_id, None)
        if callback:
            callback(urc)
        else:
            logger.debug(f'Unhandled urc: {urc}')

    def _handle_cme_error(self, urc: bytes):

        raise CMEError(urc.decode())

    def _add_available_message_callback(self, urc: bytes):
        _urc, data = urc.split(b':')
        result = data.lstrip()
        logger.debug(f'Recieved data: {result}')
        self.available_messages.append(result)

    def _update_radio_statistics(self):
        radio_data = self._at_action(self.AT_RADIO_INFORMATION)
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
        status = int(chr(urc[-1]))
        self.registration_status = status
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

    def _await_connection(self, roaming, timeout=180):

        logging.info(f'Awaiting Connection')

        if roaming:
            self._read_line_until_contains('CEREG: 5')
        else:
            self._read_line_until_contains('CEREG: 1')


class SaraR4Module(SaraN211Module):
    BAUDRATE = 115200
    RTSCTS = 1

    DEFAULT_BANDS = [20]

    AT_CREATE_UDP_SOCKET = 'AT+USOCR=17'
    AT_CREATE_TCP_SOCKET = 'AT+USOCR=6'
    AT_ENABLE_LTE_M_RADIO = 'AT+URAT=7'
    AT_ENABLE_NBIOT_RADIO = 'AT+URAT=8'
    AT_CLOSE_SOCKET = 'AT+USOCL'

    AT_REBOOT = 'AT+CFUN=15'  # R4 specific

    REBOOT_TIME = 10

    SUPPORTED_SOCKET_TYPES = ['UDP', 'TCP']

    def __init__(self, serial_port: str, roaming=False, echo=True):

        super().__init__(serial_port, roaming, echo)

    def setup(self, radio_mode='NBIOT'):
        self.set_radio_mode(mode=radio_mode)
        self.enable_radio_functions()
        self.enable_network_registration()
        self.set_error_format()
        self.set_data_format()

    def set_data_format(self):

        self._at_action('AT+UDCONF=1,1')  # Set data format to HEX
        logger.info('Data format set to HEX')

    def set_error_format(self):
        self._at_action('AT+CMEE=2')  # enable verbose errors
        logger.info('Verbose errors enabled')

    def set_band_mask(self, bands: list = None):
        """
        Band is set using a bit for each band. Band 1=bit 0, Band 64=Bit 63

        .. note:
            Only supports NB IoT RAT.
        """
        logger.info(f'Setting Band Mask for bands {bands}')
        bands_to_set = self.DEFAULT_BANDS
        if bands:
            bands_to_set = bands

        total_band_mask = 0

        for band in bands_to_set:
            individual_band_mask = 1 << (band - 1)
            total_band_mask = total_band_mask | individual_band_mask

        self._at_action(f'AT+UBANDMASK=1,{total_band_mask},{total_band_mask}')

    def set_radio_mode(self, mode):
        # TODO: Move to parent object. And have list of supported radios on object.
        mode_dict = {'NBIOT': self.AT_ENABLE_NBIOT_RADIO,
                     'LTEM': self.AT_ENABLE_LTE_M_RADIO}

        response = self._at_action(mode_dict[mode.upper()])
        logger.info(f'Radio Mode set to {mode}')
        return response

    def set_pdp_context(self, apn, pdp_type="IP", cid=1):
        logger.info(f'Setting PDP Context')
        _at_command = f'AT+CGDCONT={cid},"{pdp_type}","{apn}"'
        self._at_action(_at_command)
        logger.info(f'PDP Context: {apn}, {pdp_type}')

    def _create_upd_socket(self, port):
        at_command = f'{self.AT_CREATE_UDP_SOCKET}'
        if port:
            at_command = at_command + f',{port}'
        response = self._at_action(at_command, capture_urc=True)
        socket_id = int(chr(response[0][-1]))
        sock = UDPSocket(socket_id, self, port)
        self.sockets[sock.socket_id] = sock
        return sock

    def send_udp_data(self, host: str, port: int, data: str):
        """Send a UDP message"""
        logger.info(f'Sending UDP message to {host}:{port}  :  {data}')
        _data = binascii.hexlify(data.encode()).upper().decode()
        length = len(data)
        atc = f'AT+USOST=0,"{host}",{port},{length},"{_data}"'
        result = self._at_action(atc)
        return result

    def _await_connection(self, roaming, timeout=180):
        logging.info(f'Awaiting Connection')
        start_time = time.time()
        while True:
            time.sleep(2)
            self._at_action('AT+CEREG?')

            if self.registration_status == 0:
                continue

            if roaming:
                if self.registration_status == 5:
                    break

            else:
                if self.registration_status == 1:
                    break

            elapsed_time = time.time() - start_time
            if elapsed_time > timeout:
                raise ConnectionTimeoutError(f'Could not connect')
