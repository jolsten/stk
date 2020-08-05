# -*- coding: utf-8 -*-
"""
Created on Tue Aug  4 20:13:37 2020

@author: jolsten
"""
import sys, logging
import socket
import time

from abc import ABCMeta, abstractmethod

from .exceptions import *
from .utils import STK_DATEFMT, inherit_docstrings

class _AbstractConnect(metaclass=ABCMeta):
    '''An STK Connect connection class.
    
    Attributes:
        host : str
        
            The host on which the desired instance of STK is running.
        
        port : int
            
            The port on which the desired instance is accepting connections.
        
        address : tuple
        
            The address as a tuple (host, port)
        
        ack : bool
        
            A boolean representing whether the instance is using ACK/NACK.
            
            Changing this after .connect() is called will not change the mode.
        
        connect_attempts : int
        
            The maximum number of attempts at connecting to the socket.
        
        send_attempts : int
        
            Sets the default maximum number of attempts to make while calling 
            .send() before raising STKNackError.
        
        timeout : float
            
            Sets the default timeout period for calls to .read() before 
            assuming all data was received.
    
    '''
    def __init__(self, **kwargs):
        '''Inits an STK connection object (Connect or AsyncConnect)
        
        Args:
            host : str (default: 'localhost')
            
            port : int (default: 5001)
            
            ack : bool (default: True)
                Specifies whether or not to use ACK/NACK responses with STK 
                Connect. Highly recommended to leave this to True.
            
            connect_attempts : int (default: 5)
                The maximum number of attempts at connecting to the socket.
                
                Several attempts should be made, in case the instance of STK 
                hasn't finished initializing by the time this is called.
            
            send_attempts : int (default: 1)
                Sets the default maximum number of attempts to make while 
                calling .send() before raising STKNackError.
            
            timeout : int or float (default: 1.0)
                Sets the default timeout period for calls to .read() before 
                assuming all data was received.
                
                Because network traffic is unpredictable, increasing the 
                timeout will increase the likelihood that you receive all the 
                data.
                
                However, this also adds a mandatory minimum delay before the 
                read() function returns.
        '''
        self._kwargs = kwargs
        
        self.host               = str( kwargs.get('host', 'localhost') )
        self.port               = int( kwargs.get('port', 5001) )
        self.ack               = bool( kwargs.get('ack', True) )
        self.connect_attempts   = int( kwargs.get('connect_attempts', 5) )
        self.send_attempts      = int( kwargs.get('send_attempts', 1) )
        self.timeout          = float( kwargs.get('timeout', 1 ) )
        
        self.socket = None
    
    @property
    def address(self):
        '''The socket address tuple.
        
        Args:
            None
            
        Returns:
            tuple : (host, port)
        '''
        return (self.host, self.port)
    
    def connect(self):
        '''Connect to the STK Connect socket specified.
        
        Args:
            None
        
        Returns:
            None
        
        Raises:
            STKConnectError : If, after .connect_attempts attempts, a
            connection couldn't be made successfully.'
        '''
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        time.sleep(3) # give STK a moment to start
        self._connect()
        
        if type(self) == AsyncConnect:
            self.send(f'ConControl / AsyncOn')
        
        if self.ack is not True:
            self.send(f'ConControl / AckOff')
    
    def _connect(self):
        attempt = 0
        while True:
            attempt += 1
            try:
                self.socket.connect(self.address)
            except ConnectionRefusedError as e:
                logging.debug(f'ConnectionRefusedError: {e}')
            else: # exit loop if no exceptions caught
                logging.info(f'Connected to STK on {self.host}:{self.port}')
                return True
            finally: # continue loop if any exception caught
                if attempt >= self.connect_attempts:
                    raise STKConnectError(f'Failed to connect to STK via socket on {self.host}:{self.port}')
            time.sleep( 3 )
    
    def send(self, message, attempts=None):
        '''Sends a Connect command via socket.
        
        Args:
            message: A string containing the STK Connect command
            
            attempts: Optional; The maximum number of times to send the
                command if a NACK is received.
        
        Returns:
            None
        
        Raises:
            STKNackError : If too many NACK responses were received from STK.
        
        Examples:
            s.send("Unload / *")
        '''
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
    
    def read(self, timeout=None):
        '''Read all available data from the TCP/IP socket.
        
        Args:
            timeout : int or None (default: None)
            
                Sets the timeout period for this specific call to .read() 
                before assuming all data was received.
            
                Because network traffic is unpredictable, increasing the 
                timeout will increase the likelihood that you receive all the 
                data.
                
                However, this also adds a mandatory minimum delay before the 
                read() function returns.

        Returns:
            bytes : a bytes object containing the data received from the socket

        '''
        timeout = timeout
        if timeout is None: timeout = self.timeout
        self.socket.setblocking(False)
        self.socket.settimeout(timeout)
        
        logging.debug('Reading until no data is left in the socket...')
        
        buffer = b''
        while True:
            try:
                buffer += self.socket.recv(4096)
            except socket.timeout:
                logging.debug('Timeout reached, returning buffer')
                self.socket.settimeout(None)
                return buffer
    
    def disconnect(self):
        '''Alias of .close()'''
        self.close()
        
    def close(self):
        '''Closes the STK Connect socket.
        
        Args:
            None
        
        Returns:
            None
        '''
        try:
            self.socket.close()
        except:
            pass
    
    def __repr__(self):
        return f'{type(self).__name__}({self.host}:{self.port})'
    
    def __del__(self):
        self.close()
        
    @abstractmethod
    def get_ack(self, message):
        '''Block until an ACK is received from STK Connect.
        
        Users should not typically need to use this method directly, as it is
        called from .send() if the class attribute ack=True
        
        Args:
            None
        
        Returns:
            None
        '''
        pass
    
    @abstractmethod
    def get_single_message(self):
        pass
    
    @abstractmethod
    def get_multi_message(self):
        pass
    
    @abstractmethod
    def report(self, **kwargs):
        '''Create a report in STK and save it to a file.
        
        Args:
            ObjPath : str (required)
            
                The STK Object Path for the desired report.
                
                e.g.
                Facility/A_Facility_Name
                Satellite/A_Satellite_Name
            
            Style : str or path-like object (required)
            
                The Style name, if it is already loaded into STK (or is a 
                default report style).
                
                Otherwise, pass a path to the desired .RST file.
            
            FilePath : str or path-like object (required)
            
                The path to the file to which the report should be written.
            
            TimePeriod : str or None (default: None)
            
                The time period to use for the report.  If None, then use the 
                default (typically the parent object's time period).
                
                Valid values:
                    UseAccessTimes
                    {TimeInterval}
                    Intervals {"<FilePath>" | "<IntervalOrListSpec>"}
                    
                    Enter {TimeInterval} to define the start time and stop 
                    time for the report span. For valid {TimeInterval} values 
                    see Time Options.
                    
                    Or specify UseAccessTimes to only report data during 
                    access times between the <ObjectPath> and an AccessObject, 
                    but you must also specify at least one AccessObject.

                    Or use the Intervals option to specify an STK interval
                    file for the time period or an Interval or Interval List 
                    component specification. 
                    
                    For help on creating the STK interval file, 
                    see Create & Import External Files - Interval List 
                    in STK Help.
                    
                    For information about "<IntervalOrListSpec>" see 
                    Component Specification.
                    
                    See STK Help for more details on these options.
            
            TimeStep : float or str (default: None)
            
                The timestep to use for the report. If None, then use the 
                default (typically the parent object's timestep).
                
                Valid values:
                    <Value>
                    Bound <Value>
                    Array "<TimeArraySpec>"
                
                    Enter the time step <Value> to be used in creating the 
                    report. This value is entered in seconds and must be 
                    between 0.000001 and 1000000000.0 seconds.
                    
                    Or enter Bound <Value> to have the report steps calculated
                    on a specific time boundary. This value is entered in 
                    seconds and must be between 0 and 3600 seconds. If 0 is 
                    entered then the default time step (usually 60 seconds) is 
                    used.

                    Or enter the Array keyword with a Time Array component 
                    specification to use the array times as time steps. For 
                    information about "<TimeArraySpec>" 
                    see Component Specification.
            
            AdditionalData : str or None (default: None)
            
                Some Report Styles require additional or pre-data, such as a 
                comparison object for the RIC report for a Satellite. For these
                types of reports you must include this option. More information
                on styles that require AdditionalData can be found at "Report 
                Additional Data" in the STK Help.
            
            Summary : str or None (default: None)
            
                Summary data is not generally included. Use this option, to 
                have the summary data included in the exported report file.
                
                Valid values:
                    Include 
                    Only
                
                Specify the Include value to have the summary included with the
                rest of the report; use the Only value to have only the summary
                data reported. 
                
        Returns:
            None
        '''
        pass
    
    @abstractmethod
    def report_rm(self, **kwargs):
        '''Create a report in STK and return them via socket.
        
        Args:
            ObjPath : str (required)
            
                The STK Object Path for the desired report.
                
                e.g.
                Facility/A_Facility_Name
                Satellite/A_Satellite_Name
            
            Style : str or path-like object (required)
            
                The Style name, if it is already loaded into STK (or is a 
                default report style).
                
                Otherwise, pass a path to the desired .RST file.
            
            TimePeriod : str or None (default: None)
            
                The time period to use for the report.  If None, then use the
                default (typically the parent object's time period).
                
                Valid values:
                    UseAccessTimes
                    {TimeInterval}
                    Intervals {"<FilePath>" | "<IntervalOrListSpec>"}
                    
                    Enter {TimeInterval} to define the start time and stop time
                    for the report span. For valid {TimeInterval} values see
                    Time Options.
                    
                    Or specify UseAccessTimes to only report data during access
                    times between the <ObjectPath> and an AccessObject, but you
                    must also specify at least one AccessObject.

                    Or use the Intervals option to specify an STK interval file
                    for the time period or an Interval or Interval List 
                    component specification. 
                    
                    For help on creating the STK interval file, see Create & 
                    Import External Files - Interval List in STK Help.
                    
                    For information about "<IntervalOrListSpec>" 
                    see Component Specification.
                    
                    See STK Help for more details on these options.
            
            TimeStep : float or str
            
                The timestep to use for the report. If None, then use the 
                default (typically the parent object's timestep).
                
                Valid values:
                    <Value>
                    Bound <Value>
                    Array "<TimeArraySpec>"
                
                    Enter the time step <Value> to be used in creating the 
                    report. This value is entered in seconds and must be 
                    between 0.000001 and 1000000000.0 seconds.
                    
                    Or enter Bound <Value> to have the report steps calculated
                    on a specific time boundary. This value is entered in 
                    seconds and must be between 0 and 3600 seconds. If 0 is 
                    entered then the default time step (usually 60 seconds) is 
                    used.

                    Or enter the Array keyword with a Time Array component 
                    specification to use the array times as time steps. For 
                    information about "<TimeArraySpec>" 
                    see Component Specification.
            
            AdditionalData : 
                
                Some Report Styles require additional or pre-data, such as a 
                comparison object for the RIC report for a Satellite. For these
                types of reports you must include this option. More information
                on styles that require AdditionalData can be found at 
                "Report Additional Data" in the STK Help.
                
            Summary : str
                
                Valid values:
                    Include 
                    Only
                    
                    Summary data is not generally included. Use this option, to
                    have the summary data included in the exported report file.
                    Specify the Include value to have the summary included with
                    the rest of the report; use the Only value to have only the
                    summary data reported. 
                    
        Returns:
            None
        '''
        pass


class Connect(_AbstractConnect):
    @inherit_docstrings
    def get_ack(self, message):
        msg = self.socket.recv(3).decode()
        if msg == 'ACK':
            logging.debug('ACK Received')
            return
        elif msg == 'NAC':
            k = self.socket.recv(1).decode()
            msg = msg + k
            raise STKNackError(f'NACK Received: stk.send("{message.rstrip()}")')
        else:
            logging.error(f'Expecting ACK or NACK, got: {msg}{self.socket.recv(2048)}')
            sys.exit(1)
    
    def get_single_message(self):
        header = self.socket.recv(40).decode()
        cmd_name, length = header.rstrip().split()
        length = int(length)
        data = self.socket.recv(length).decode()
        return header, data
    
    def get_multi_message(self):
        hdr, data = self.get_single_message()
        
        messages = []
        for i in range(int(data)):
            sm = self.get_single_message()
            if len(sm) > 0:
                messages.append(sm)
        return messages
    
    @inherit_docstrings
    def report(self, ObjPath, Style, FilePath, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None):
        message = f'ReportCreate */{ObjPath} Style "{Style}" Type "Export" File "{FilePath}"'
        if AccessObjectPath is not None: message += f' AccessObject {AccessObjectPath}'
        if TimePeriod       is not None: message += f' TimePeriod {TimePeriod}'
        if TimeStep         is not None: message += f' TimeStep {TimeStep}'
        if AdditionalData   is not None: message += f' AdditionalData "{AdditionalData}"'
        if Summary          is not None: message += f' Summary {Summary}'
        if AllLines         is not None: message += f' AllLines {AllLines}'
        
        self.send(message)
    
    @inherit_docstrings
    def report_rm(self, ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None, **kwargs):
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
        
        logging.debug(f'Report_RM Returned: {buffer}')
        return []


class AsyncConnect(_AbstractConnect):
    @inherit_docstrings
    def get_ack(self, message):
        hdr, data = self.get_single_message()
        if hdr.async_type == 'ACK':
            return True
        elif hdr.async_type == 'NACK':
            raise STKNackError(f'NACK Received: stk.send("{message}")')
    
    def get_single_message(self):
        msg = self.socket.recv(42).decode()
        hdr = AsyncHeader(msg)
        
        pdl = hdr.data_length
        data = self.socket.recv( pdl ).decode()
        while len(data) < hdr.data_length:
            data += self.socket.recv( pdl - len(data) ).decode()
        
        return hdr, data
    
    def get_multi_message(self):
        logging.debug('Getting Message Block:')
        hdr, data = self.get_single_message()
        
        logging.debug(f'GotMessage: {hdr}{data}')
        msg_grp = [None] * hdr.total_packets
        msg_grp[hdr.packet_number-1] = data
        
        for i in range(1,hdr.total_packets):
            hdr, data = self.get_message()
            logging.debug(f'GotMessage: {hdr}{data}')
            msg_grp[hdr.packet_number-1] = data
        
        if msg_grp[-1] == '': del msg_grp[-1]
        return msg_grp
    
    @inherit_docstrings
    def report(self, ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None):
        message = f'ReportCreate */{ObjPath} Style "{Style}"'
        if AccessObjectPath is not None: message += f' AccessObject {AccessObjectPath}'
        if TimePeriod       is not None: message += f' TimePeriod {TimePeriod}'
        if TimeStep         is not None: message += f' TimeStep {TimeStep}'
        if AdditionalData   is not None: message += f' AdditionalData "{AdditionalData}"'
        if Summary          is not None: message += f' Summary {Summary}'
        if AllLines         is not None: message += f' AllLines {AllLines}'
        
        self.send(message)
    
    @inherit_docstrings
    def report_rm(self, ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None, **kwargs):
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


class AsyncHeader():
    '''A helper class to read the STK Connect Asynchronous Message Format headers.'''
    
    def __init__(self, bytestring):
        '''Inits a new object using the raw values, passed as bytes or str.'''
        if isinstance(bytestring, bytes): bytestring = bytestring.decode()
        self.raw = bytestring
    
    def __repr__(self):
        return f'<{self.raw}>'
    
    @property
    def sync(self):
        '''str : The sync word, should always be "AGI"'''
        return self.raw[0:3].decode()
    
    @property
    def header_length(self):
        '''int : The header_length, should always be 42.'''
        return int(self.raw[3:5].decode())
    
    @property
    def version(self):
        '''str : The version in major.minor format.'''
        return f'{self.major_version}.{self.minor_version}'
    
    @property
    def major_version(self):
        '''int : The major version number.'''
        return int(self.raw[5].decode())
    
    @property
    def minor_version(self):
        '''int : The minor version number.'''
        return int(self.raw[6].decode())
    
    @property
    def type_length(self):
        '''int : The length of the command type string.'''
        return int(self.raw[7:9])
    
    @property
    def async_type(self):
        '''str : The value of the command type string.'''
        return (self.raw[9:24])[0:self.type_length]
    
    @property
    def identifier(self):
        '''int : The value of the response ID.
        
            This should be used to associate the correct responses with each 
            other if commands are being processed asynchronously.
        '''
        
        return int(self.raw[24:30])
    
    @property
    def total_packets(self):
        '''int : The total number of packets in the current identifier.'''
        return int(self.raw[30:34])
    
    @property
    def packet_number(self):
        '''int : The sequence number of the current packet for this identifier.'''
        return int(self.raw[34:38])
    
    @property
    def data_length(self):
        '''int : The length of the data field for the current packet.'''
        return int(self.raw[38:42])
