import sys
import socket
import logging
import time
import subprocess
import platform
import collections
import os
from pathlib import Path

STK_DATEFMT = '%d %b %Y %H:%M:%S.%f'

SingleMessage = collections.namedtuple('SingleMessage', ['Command', 'Data'])
MultiMessage  = collections.namedtuple('MultiMessage' , ['Command', 'Data'])

def get_open_port():
    with socket.socket() as s:
        s.bind(('', 0))
        return s.getsockname()[1]

from threading import Thread
from queue import Queue, Empty
ON_POSIX = 'posix' in sys.builtin_module_names
def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()    

class STKConnect():
    '''
    Connect to an (already running) instance of Systems ToolKit via socket
    
    Attributes
    ----------
    host : str (default:localhost)
        the hostname of the instance of STK (default: localhost)
    
    port : int
        the port number for the STK socket (default: 5001)
    
    Methods
    -------
    connect()
        attempts to connect to STK via a socket
    
    send(message)
        sends the specified message to STK 
    
    close()
        closes the socket, if it is open
    
    Examples
    --------
    s = STKConnect()
    s.connect()
    s.send('Unload / *')
    s.send(f'New / Scenario Scenario_Name')
    s.close()
    '''
    def __init__(self, host='localhost', port=5001, max_attempts=5, retry_time=3):
        self.host = host
        self.port = int(port)
        self.max_attempts = int(max_attempts)
        self.retry_time = int(retry_time)
    
    def connect(self, **kwargs):
        for key, value in kwargs.items(): setattr(self, key, value)
        
        address = (self.host, self.port)
        
        if hasattr(self,'socket') and type(self.socket) == 'socket':
            logging.warning('Already connected to an STK socket!')
            return
        else:
            self.socket = socket.socket()
            attempts = 0
            while True:
                attempts += 1
                try:
                    self.socket.connect(address)
                except ConnectionRefusedError as e:
                    logging.debug(f'Exception caught: {e}')
                else: # exit loop if no exceptions caught
                    logging.info(f'Connected to STK on {self.host}:{self.port}')
                    return
                finally: # continue loop if any exception caught
                    if attempts >= self.max_attempts: raise OSError(f'Could not connect to STK via socket on {self.host}:{self.port}')
                    time.sleep(self.retry_time)
    
    def send(self, message):
        try:
            logging.debug('stk.send("%s")' % message)
            message += "\n"
            self.socket.send(message.encode())
            self.get_ack(message)
        except Exception as msg:
            logging.error('socket send error: %s' % msg)
            exit(1)
    
    def close_socket(self):
        if hasattr(self, 'socket'):
            logging.debug('closing socket')
            self.socket.close()
            del self.socket
    
    def close(self):
        self.close_socket()
    
    def get_ack(self, message):
        try:
            msg = self.socket.recv(3).decode()
            if msg == 'ACK':
                # logging.debug('ACK Received')
                return 1
            elif msg == 'NAC':
                k = self.socket.recv(1).decode()
                msg = msg + k
                raise Exception('NACK Received: stk.send("%s")' % message.rstrip())
                exit(1)
            else:
                logging.error('received neither ACK nor NACK')
                sys.exit(1)
        except Exception as msg:
            logging.error('get_ack raised exception: %s' % msg)
    
    def aer(self, fm, to, maxstepsize=None, minstepsize=None, fixedsamplestep=None, eventsbasedonsamples=None):
        cmd = 'AER %s %s' % (fm, to)
        if maxstepsize:             cmd = cmd + ' MaxStepSize %f' % float(maxstepsize)
        if minstepsize:             cmd = cmd + ' MinStepSize %f' % float(minstepsize)
        if fixedsamplestep:         cmd = cmd + ' FixedSampleStep %f' % float(fixedsamplestep)
        if eventsbasedonsamples:    cmd = cmd + ' EventsBasedOnSamples %s' % eventsbasedonsamples
        self.send(cmd)
        
        return self.get_aer()
    
    def get_aer(self):
        msg = self.socket.recv(40).decode()
        msg.rstrip()
        things = msg.split(' ', maxsplit=1)
        name = str(things[0])
        size = int(things[1])
    
        ptr = 0
        report = ''
        while ptr < size:
            msg = self.socket.recv(2048).decode()
            report = report + msg
            ptr += 2048
        
        return report
    
    def get_single_message(self):
        header = self.socket.recv(40).decode()
        cmd_name, length = header.rstrip().split()
        length = int(length)
        data = self.socket.recv(length).decode()
        return data
    
    def get_multi_message(self):
        header = self.socket.recv(40).decode()
        cmd_name, length = header.rstrip().split()
        data = self.socket.recv(int(length)).decode()
        
        messages = []
        for i in range(int(data)):
            sm = self.get_single_message()
            if len(sm) > 0:
                messages.append(sm)
        return messages
    
    def __repr__(self):
        return 'stk.stk(host: %s, port: %s)' % (self.host, self.port)
    
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
    
    max_attempts : int (default: 15 attempts)
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
    def __init__(self, host='localhost', port='auto', max_attempts=15, poll_period=3, stk_install_dir=None, stk_config_dir=None, vendorid=None, loglevel=None):
        self.path               = self._stk_install_dir(stk_install_dir).expanduser()
        self.host               = host
        self.port               = port
        self.max_attempts       = int(max_attempts)
        self.poll_period        = int(poll_period)
        self.vendorid           = vendorid
        self.stk_install_dir    = Path(stk_install_dir).expanduser().resolve()
        self.stk_config_dir     = Path(stk_config_dir).expanduser().resolve()
        self.loglevel           = loglevel
        
        self.process = None
        self.connect = None
        
        self.launch()
        
        logging.debug('Sleeping for 5 to give STK a chance to launch')
        time.sleep(5)
    
    def launch(self):
        if platform.system() == 'Linux':
            attempts = 0
            while True:
                attempts += 1
                try:
                    self._launch_linux()
                except subprocess.CalledProcessError as e:
                    logging.error(f'exception caught: {e}')
                else:
                    return
                finally:
                    if attempts >= self.max_attempts: raise subprocess.CalledProcessError(69, self._process_call)
                    time.sleep(self.poll_period)
                
        elif platform.system() == 'Windows':
            self._launch_windows()
    
    def _launch_linux(self):
        app_path = self.path / 'bin' / 'connectconsole'
        
        if self.port == 'auto': self.port = get_open_port()
        
        call = [
            str(app_path),
            '--port', str(self.port),
            '--noGraphics',
        ]
        if self.vendorid: call.extend(['--vendorid', str(self.vendorid)])
        if self.loglevel: call.extend(['--log', 'information'])
        
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
        
        attempts = 0
        while True:
            attempts += 1
            try:
                line = self._queue.get_nowait().decode().rstrip()
            except Empty:
                logging.debug(f'no output yet')
            except OSError:
                pass
            else:
                logging.debug(f'got output from STK: {line}')
                if 'STK/CON: Accepting connection requests' in line:
                    logging.info('Successfully started STK, it is accepting connection requests')
                    logging.info('Attempting to connect via socket at {self.host}:{self.port}')
                    try:
                        self.connect = STKConnect(host=self.host, port=self.port)
                        self.connect.connect()
                    except OSError:
                        pass
                    else:
                        return
            finally:
                if attempts >= self.max_attempts: raise subprocess.CalledProcessError(66, ' '.join(call))
                time.sleep(self.poll_period)
                
    
    def _launch_windows(self):
        self.port = 5001
        app_path = self.path / 'bin' / 'AgUiApplication.exe'
        call = [str(app_path), '/pers', 'STK']
        self.process = subprocess.Popen(call)
    
    def send(self, message):
        self.connect.send(message)
    
    def close(self):
        self._close_connect()
        if hasattr(self, 'process') and self.process is not None:
            logging.debug('Killing STK process')
            self.process.kill()
    
    def _close_connect(self):
        if hasattr(self, 'connect') and self.connect is not None:
            logging.debug('Closing STK Connect socket')
            self.connect.close()
    
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
