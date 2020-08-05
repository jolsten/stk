import os, sys, logging
import subprocess
import platform
import time
from pathlib import Path

from .connect import Connect, AsyncConnect
from .exceptions import *
from .utils import STK_DATEFMT

from threading import Thread
from queue import Queue, Empty
ON_POSIX = 'posix' in sys.builtin_module_names
def _enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

def _default_install_dir():
    if platform.system() == 'Linux':
        for directory in ['~/stk']:
            path = Path( os.path.expandvars( Path(directory).expanduser().resolve() ) )
            logging.debug(f'Is STK_INSTALL_DIR at {path} ?')
            if path.is_dir() and (path / 'bin' / 'connectconsole').is_file():
                logging.debug('Yes, it is!')
                return path
    elif platform.system() == 'Windows':
        for directory in ['%PROGRAMFILES%\AGI\STK 12', '%PROGRAMFILES%\AGI\STK 11', '%PROGRAMFILES%\AGI\STK 10']:
            path = Path( os.path.expandvars( Path(directory).expanduser().resolve() ) )
            logging.debug(f'Is STK_INSTALL_DIR at {path} ?')
            if path.is_dir() and (path / 'bin' / 'AgUiApplication.exe').is_file():
                logging.debug('Yes, it is!')
                return path
    raise FileNotFoundError('STK_INSTALL_DIR was not provided as an argument, environment variable -- or was not found in the location specified')

def _default_config_dir():
    return Path('~/STK').expanduser().resolve()

class Run():
    '''
    Run an instance of AGI's Systems ToolKit (STK), and connect via socket
    
    Attributes
    ----------
    host : str (default: localhost)
        the hostname of the instance of STK (default: localhost)
    
    port : int (default: 5001)
        the port number for the STK socket (default: 5001)
    
    stk_install_dir : path-like object
        the path to the relevant STK executable
        
        Defaults: 
            Windows: %PROGRAMFILES%\\AGI\\STK 12
                     %PROGRAMFILES%\\AGI\\STK 11
            Linux  : ~/stk
    
    stk_config_dir : path-like object (default: ~/STK)
        the path to the desired STK configuration directory
        
    vendorid : str
        STK license Vendor ID; apparently necessary in a Linux environment
    
    ack : bool (default: True)
        determines whether or not ACK/NACK responses are used in interacting
        with STK via Connect command
    
    run_attempts : int (default: 1)
        maximum number of times to attempt to run an instance of STK
    
    connect_attempts : int (default: 5)
        maximum number of times to attempt connecting to STK socket
        
    send_attempts : int (default: 1)
        maximum number of attempts for each STK Connect message before a NACK
        throws an exception
    
    port_delta : int (default: 1000)
        in instances where STK cannot bind to the desired port, this value is
        the number added to the port specified above before attempting to run
        STK again
    
    
    Methods
    -------
    run(), launch()
        launch an instance of the STK application
    
    send(message)
        sends the specified message to STK
    
    report(ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None)
    
    
    report_rm(ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None, timeout=None)
        
    
    disconnect()
        closes the socket, if it is open
    
    close()
        shut down the STK application
    '''
    def __init__(self, **kwargs):
        self._kwargs = kwargs
        
        self.host             =   str( kwargs.get('host', 'localhost'     ) )
        self.port             =   int( kwargs.get('host', 5001            ) )
        self.vendorid         =   str( kwargs.get('vendorid',         None) )
        self.port_delta       =   int( kwargs.get('port_delta',       1000) )
        self.ack              =  bool( kwargs.get('ack',              True) )
        self.run_attempts     =   int( kwargs.get('run_attempts',        1) )
        self.connect_attempts =   int( kwargs.get('connect_attempts',    5) )
        self.send_attempts    =   int( kwargs.get('send_attempts',       1) )
        self.timeout          = float( kwargs.get('timeout',             1) )
        self.async_messaging  =  bool( kwargs.get('async_messaging', False) )

        
        self.stk_install_dir    = kwargs.get('stk_install_dir', os.environ.get('STK_INSTALL_DIR', _default_install_dir() ))
        self.stk_config_dir     = kwargs.get('stk_install_dir', os.environ.get('STK_CONFIG_DIR' , _default_config_dir()  ))
        
        self.stk_install_dir    = Path(self.stk_install_dir).expanduser().resolve()
        self.stk_config_dir     = Path(self.stk_config_dir ).expanduser().resolve()
        
        self._process = None
        self._connect = None
    
    def launch(self):
        self.run()
    
    def run(self):
        if platform.system() == 'Linux':
            attempts = 0
            while True:
                attempts += 1
                try:
                    logging.debug(f'Attempting to Launch STK & Connect ({attempts} of {self.max_attempts}) on {self.host}:{self.port}')
                    
                    running_procs = subprocess.check_output(['ps', 'aux'])
                    logging.debug(f'current running connectconsole processes:\n{running_procs}')
                    
                    self._launch_linux()
                    return
                except Exception as e:
                    logging.error(f'Exception caught: {e}')
                    try: self._process.kill()
                    except: pass
                finally:
                    if attempts >= self.max_attempts: 
                        logging.critical(f'Attempted to launch STK, exceeded max attempts ({self.max_attempts})')
                        raise subprocess.CalledProcessError(1, self._process_call)
                
                time.sleep( 3 )
                
        elif platform.system() == 'Windows':
            self._launch_windows()
    
    def connect(self):
        if self.async_messaging:
            self._connect = AsyncConnect(**self._kwargs)
        else:
            self._connect = Connect(**self._kwargs)
        self._connect.connect()
    
    def _launch_linux(self):
        app_path = Path(self.stk_install_dir) / 'bin' / 'connectconsole'
        
        call = [
            str(app_path),
            '--port', str(self.port),
            '--noGraphics',
        ]
        if self.vendorid: call.extend(['--vendorid', str(self.vendorid)])
        
        env = {}
        env.update(os.environ)
        env['STK_INSTALL_DIR'] = str(self.stk_install_dir)
        env['LD_LIBRARY_PATH'] = f'''$STK_INSTALL_DIR/bin:{env['LD_LIBRARY_PATH']}'''
        env['STK_CONFIG_DIR']  = str(self.stk_config_dir)

        self._process = subprocess.Popen(call, env=env, stderr=subprocess.PIPE, bufsize=1, close_fds=ON_POSIX)
        self._process_call = ' '.join(call)
        
        self._queue = Queue()
        self._thread = Thread(target=_enqueue_output, args=(self._process.stderr, self._queue))
        self._thread.daemon = True
        self._thread.start()
        
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
                    return
            finally:
                if attempts >= self.run_attempts:
                    logging.debug('Killing STK Popen to retry')
                    self._process.kill()
                    raise subprocess.CalledProcessError(2, f'' + ' '.join(call))
                
    def _launch_windows(self):
        self.port = 5001
        app_path = Path(self.stk_install_dir) / 'bin' / 'AgUiApplication.exe'
        call = [str(app_path), '/pers', 'STK']
        self._process = subprocess.Popen(call)
    
    def send(self, message, attempts=1):
        try:
            self._connect.send(message, attempts=attempts)
        except STKNackError:
            self._dump_stk_errors()
    
    def close(self):
        self.disconnect()
        if self._process is not None:
            logging.debug('Killing STK process')
            self._process.kill()
    
    def disconnect(self):
        if self._connect is not None:
            logging.debug('Closing STK Connect socket')
            self._connect.close()
    
    def _dump_stk_errors(self):
        logging.critical('Dumping STK STDERR:')
        while True:
            try:
                line = self._queue.get_nowait().decode().rstrip()
                logging.critical(f'STK Said: {line}')
            except Empty:
                return
    
    def __del__(self):
        logging.debug('Cleaning up STK process')
        self.close()
    
    def report(self, *args, **kwargs):
        try:
            return self._connect.report(*args, **kwargs)
        except STKNackError:
            logging.warning('STK NACK on ReportCreate')
            if hasattr(self, '_queue'): self._dump_stk_errors()
    
    def report_rm(self, *args, **kwargs):
        try:
            return self._connect.report_rm(*args, **kwargs)
        except STKNackError:
            logging.warning('STK NACK on Report_RM')
            if hasattr(self, '_queue'): self._dump_stk_errors()
    
