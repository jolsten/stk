import sys
import socket
import logging
import time
import subprocess
import platform
import os
from pathlib import Path

STK_DATEFMT = '%d %b %Y %H:%M:%S.%f'
_DEFAULT_TIMEOUT = 1

from threading import Thread
from queue import Queue, Empty
ON_POSIX = 'posix' in sys.builtin_module_names
def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

class STKLicenseError(RuntimeError):
    pass

class STKConnectError(RuntimeError):
    pass

class STKNackError(IOError):
    pass

class AsyncHeader():
    def __init__(self, bytestring):
        if isinstance(bytestring, bytes): bytestring = bytestring.decode()
        self.raw = bytestring
    
    def __repr__(self):
        return f'<{self.raw}>'
    
    @property
    def sync(self):
        return self.raw[0:3].decode()
    
    @property
    def header_length(self):
        return int(self.raw[3:5].decode())
    
    @property
    def version(self):
        return f'{self.major_version}.{self.minor_version}'
    
    @property
    def major_version(self):
        return int(self.raw[5].decode())
    
    @property
    def minor_version(self):
        return int(self.raw[6].decode())
    
    @property
    def type_length(self):
        return int(self.raw[7:9])
    
    @property
    def async_type(self):
        return (self.raw[9:24])[0:self.type_length]
    
    @property
    def identifier(self):
        return int(self.raw[24:30])
    
    @property
    def total_packets(self):
        return int(self.raw[30:34])
    
    @property
    def packet_number(self):
        return int(self.raw[34:38])
    
    @property
    def data_length(self):
        return int(self.raw[38:42])
    
class STKConnect():
    def __init__(self, host='localhost', port=5001, connect_attempts=5, send_attempts=1, timeout=_DEFAULT_TIMEOUT, ack=True):
        self.host               = str(host)
        self.port               = int(port)
        self.connect_attempts   = int(connect_attempts)
        self.send_attempts      = int(send_attempts)
        self.ack                = bool(ack)
        self.timeout            = timeout
        
        self.socket = None
    
    @property
    def address(self):
        return (self.host, self.port)

    def connect(self, host=None, port=None):
        if host is not None: self.host = str(host)
        if port is not None: self.port = int(port)
        
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._connect()
        
        self.send('ConControl / AsyncOn')
    
    def _connect(self):
        attempt = 0
        while True:
            attempt += 1
            try:
                self.socket.connect(self.address)
            except ConnectionRefusedError as e:
                logging.debug(f'Exception caught: {e}')
            else: # exit loop if no exceptions caught
                logging.info(f'Connected to STK on {self.host}:{self.port}')
                return True
            finally: # continue loop if any exception caught
                if attempt >= self.connect_attempts:
                    raise STKConnectError(f'Failed to connect to STK via socket on {self.host}:{self.port}')
            time.sleep( 3 )
    
    def send(self, message, attempts=None):
        if attempts is None: attempts = self.send_attempts
        
        attempt = 0
        while True:
            attempt += 1
            try:
                self._send(message)
                if self.ack: self.get_ack(message)
                return
            except STKNackError as e:
                if attempt >= attempts:
                    logging.error(f'send() failed, received NACK too many times')
                    raise STKNackError(e)
    
    def _send(self, message: str):
        logging.debug(f'stk.send("{message}")')
        self.socket.send( (message+'\n').encode() )
    
    def get_message(self):
        msg = self.socket.recv(42).decode()
        hdr = AsyncHeader(msg)
        
        pdl = hdr.data_length
        data = self.socket.recv( pdl ).decode()
        while len(data) < hdr.data_length:
            data += self.socket.recv( pdl - len(data) ).decode()
        
        return hdr, data
    
    def get_messages(self):
        logging.debug('Getting Message Block:')
        hdr, data = self.get_message()
        
        logging.debug(f'GotMessage: {hdr}{data}')
        msg_grp = [None] * hdr.total_packets
        msg_grp[hdr.packet_number-1] = data
        
        for i in range(1,hdr.total_packets):
            hdr, data = self.get_message()
            logging.debug(f'GotMessage: {hdr}{data}')
            msg_grp[hdr.packet_number-1] = data
        
        if msg_grp[-1] == '': del msg_grp[-1]
        return msg_grp
    
    def read(self):
        self.socket.setblocking(False)
        self.socket.settimeout(self.timeout)
        
        logging.debug('Reading until no data is left in the socket...')
        
        buffer = b''
        while True:
            try:
                buffer += self.socket.recv(4096)
            except socket.timeout:
                logging.debug('Timeout reached, returning buffer')
                self.socket.settimeout(None)
                return buffer
    
    def get_ack(self, message):
        hdr, data = self.get_message()
        if hdr.async_type == 'ACK':
            return True
        elif hdr.async_type == 'NACK':
            raise STKNackError(f'NACK Received: stk.send("{message}")')
            
    def report(self, ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None, **kwargs):
        message = f'Report_RM */{ObjPath} Style "{Style}"'
        if AccessObjectPath is not None: message += f' AccessObject {AccessObjectPath}'
        if TimePeriod       is not None: message += f' TimePeriod {TimePeriod}'
        if TimeStep         is not None: message += f' TimeStep {TimeStep}'
        if AdditionalData   is not None: message += f' AdditionalData "{AdditionalData}"'
        if Summary          is not None: message += f' Summary {Summary}'
        if AllLines         is not None: message += f' AllLines {AllLines}'
        
        self.send(message)
        
        buffer = self.read(**kwargs).decode()
        if len(buffer) == 0: return []
        
        return [  x[18:] for x in buffer.split('AGI421009REPORT_RM      ')[1:]  ]
    
    def close(self):
        try:
            self.socket.close()
        except:
            pass
    
    def __repr__(self):
        return f'STKConnect({self.host}:{self.port})'
    
    def __del__(self):
        self.close()

class STKLaunch():
    '''
    Launch an instance of AGI's Systems ToolKit (STK) and connect via socket
    
    Attributes
    ----------
    host : str (default: localhost)
        the hostname of the instance of STK (default: localhost)
    
    port : int (default: 5001)
        the port number for the STK socket (default: 5001)
    
    stk_install_dir : path-like object
        the path to the relevant STK executable
        
        Defaults: 
            Windows: C:\\Program Files\\AGI\\STK 11
            Linux  : ~/stk
    
    vendorid : str
        STK license Vendor ID; apparently necessary in a Linux environment
    
    max_attempts : int (default: 5 attempts)
        maximum number of times to attempt connecting to STK
        generally, this is a way to wait for STK to complete launching before
        the port is made available for connections
    
    poll_period : int (default: 2 seconds)
        time to wait between attempting to connect to the socket
    
    
    Methods
    -------
    launch()
        launch an instance of the STK application
    
    send(message)
        sends the specified message to STK 
    
    close_socket()
        closes the socket, if it is open
    
    close()
        shut down the STK application
    '''
    def __init__(self, host='localhost', port=5001, max_attempts=5, stk_install_dir=None, stk_config_dir='~/', vendorid=None, port_delta=1000, timeout=1):
        self.path               = self._stk_install_dir(Path(stk_install_dir)).expanduser()
        self.host               = host
        self.port               = int(port)
        self.max_attempts       = int(max_attempts)
        self.vendorid           = str(vendorid)
        self.stk_install_dir    = Path(stk_install_dir).expanduser().resolve()
        self.stk_config_dir     = Path(stk_config_dir ).expanduser().resolve()
        self.port_delta         = int(port_delta)
        
        self._timeout           = timeout
        
        self.process  = None
        self._connect = None
    
    def launch(self):
        if platform.system() == 'Linux':
            attempts = 0
            while True:
                attempts += 1
                try:
                    logging.debug(f'Attempting to Launch STK & Connect ({attempts} of {self.max_attempts}) on {self.host}:{self.port}')
                    logging.debug(f'''localhost = {os.environ.get('HOST', None)}''')
                    
                    running_procs = subprocess.check_output(['ps', 'aux'])
                    
                    logging.debug(f'current running connectconsole processes:\n{running_procs}')
                    self._launch_linux()
                except Exception as e:
                    logging.error(f'Exception caught: {e}')
                    try: self.process.kill()
                    except: pass
                else:
                    return
                finally:
                    if attempts >= self.max_attempts: 
                        logging.critical(f'Attempted to launch STK, exceeded max attempts ({self.max_attempts})')
                        raise subprocess.CalledProcessError(69, self._process_call)
                time.sleep( 3 )
                
        elif platform.system() == 'Windows':
            self._launch_windows()
    
    def connect(self):
        self._connect = STKConnect(host=self.host, port=self.port, timeout=_DEFAULT_TIMEOUT)
        self._connect.connect()
    
    def _launch_linux(self):
        app_path = self.path / 'bin' / 'connectconsole'
        
        call = [
            str(app_path),
            '--port', str(self.port),
            '--noGraphics',
        ]
        if self.vendorid: call.extend(['--vendorid', str(self.vendorid)])
        
        env = {}
        env.update(os.environ)
        env['STK_INSTALL_DIR'] = self.path
        env['LD_LIBRARY_PATH'] = f'''{self.path}/bin:{env['LD_LIBRARY_PATH']}'''
        env['STK_CONFIG_DIR']  = str(self.stk_config_dir)

        self.process = subprocess.Popen(call, env=env, stderr=subprocess.PIPE, bufsize=1, close_fds=ON_POSIX)
        self._process_call = ' '.join(call)
        
        self._queue = Queue()
        self._thread = Thread(target=enqueue_output, args=(self.process.stderr, self._queue))
        self._thread.daemon = True
        self._thread.start()
        
        self._successfully_launched = False
        attempts = 0
        while True:
            attempts += 1
            try:
                line = self._queue.get_nowait().decode().rstrip()
            except Empty:
                logging.debug(f'No output from STK yet')
                time.sleep( 3 )
            else:
                logging.debug(f'Got output from STK: {line}')
                if 'STK Engine Runtime license not found' in line:
                    raise STKLicenseError('STK Engine Runtime license not found')
                elif 'STK/CON: Error binding to socket, error' in line:
                    logging.debug(f'STK could not bind to port={self.port}, setting port={self.port+self.port_delta} for retry')
                    self.port += self.port_delta
                    logging.debug(f'Changing port number to port={self.port}')
                    raise OSError('STK/CON: Error binding to socket, error')
                elif 'STK/CON: Accepting connection requests' in line:
                    logging.debug(f'Successfully started STK, it is accepting connection requests at {self.host}:{self.port}')
                    return True
            finally:
                if attempts >= 5:
                    logging.debug('Killing STK Popen to retry')
                    self.process.kill()
                    raise subprocess.CalledProcessError(66, ' '.join(call))
                
    
    def _launch_windows(self):
        self.port = 5001
        app_path = self.path / 'bin' / 'AgUiApplication.exe'
        call = [str(app_path), '/pers', 'STK']
        self.process = subprocess.Popen(call)
    
    def send(self, message, attempts=1):
        try:
            self._connect.send(message, attempts=attempts)
        except STKNackError:
            self._dump_stk_errors()
    
    def report(self, *args, **kwargs):
        try:
            return self._connect.report(*args, **kwargs)
        except STKNackError:
            logging.warning('STK NACK on Report_RM')
            if hasattr(self, '_queue'): self._dump_stk_errors()
    
    def close(self):
        self._close_connect()
        if hasattr(self, 'process') and self.process is not None:
            logging.debug('Killing STK process')
            self.process.kill()
    
    def _dump_stk_errors(self):
        logging.critical('Dumping STK STDERR:')
        while True:
            try:
                line = self._queue.get_nowait().decode().rstrip()
                logging.critical(f'STK Said: {line}')
            except Empty:
                return
    
    def _close_connect(self):
        if hasattr(self, 'connect') and self._connect is not None:
            logging.debug('Closing STK Connect socket')
            self._connect.close()
    
    def _stk_install_dir(self, arg):
        if arg is None:
            if 'STK_INSTALL_DIR' in os.environ:
                return Path(os.environ['STK_INSTALL_DIR'])
            else:
                raise ValueError('STK_INSTALL_DIR environment variable must be set, or the stk_install_dir keyword argument must be passed to this class')
        elif isinstance(arg, str):
            arg = Path(arg)
            if not arg.is_dir(): raise FileNotFoundError
            return arg
        elif isinstance(arg, Path):
            return arg
        else:
            raise TypeError
    
    def __del__(self):
        logging.debug('Cleaning up STK process')
        self.close()
