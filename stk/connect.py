# -*- coding: utf-8 -*-
"""
Created on Tue Aug  4 20:13:37 2020

@author: jolst
"""
import sys, logging
import socket
import time

from abc import ABC, abstractmethod

from .exceptions import *
from .utils import STK_DATEFMT

class AbstractConnect(ABC):
    def __init__(self, **kwargs):
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
        return (self.host, self.port)
    
    def connect(self):
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
        self.close()
        
    def close(self):
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
        pass
    
    @abstractmethod
    def get_single_message(self):
        pass
    
    @abstractmethod
    def get_multi_message(self):
        pass
    
    @abstractmethod
    def report(self, **kwargs):
        pass
    
    @abstractmethod
    def report_rm(self, **kwargs):
        pass


class Connect(AbstractConnect):
    def __init__(self, **kwargs):
        if kwargs.get('async_messaging', False) and type(self) == Connect:
            return AsyncConnect(**kwargs)
        super().__init__(**kwargs)
    
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
    
    def report(self, ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None):
        message = f'ReportCreate */{ObjPath} Style "{Style}"'
        if AccessObjectPath is not None: message += f' AccessObject {AccessObjectPath}'
        if TimePeriod       is not None: message += f' TimePeriod {TimePeriod}'
        if TimeStep         is not None: message += f' TimeStep {TimeStep}'
        if AdditionalData   is not None: message += f' AdditionalData "{AdditionalData}"'
        if Summary          is not None: message += f' Summary {Summary}'
        if AllLines         is not None: message += f' AllLines {AllLines}'
        
        self.send(message)

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


class AsyncConnect(AbstractConnect):
    def __init__(self, **kwargs):
        self._kwargs = kwargs
        
        self.host               = str( kwargs.get('host', 'localhost') )
        self.port               = int( kwargs.get('port', 5001) )
        self.ack               = bool( kwargs.get('ack', True) )
        self.connect_attempts   = int( kwargs.get('connect_attempts', 5) )
        self.send_attempts      = int( kwargs.get('send_attempts', 1) )
        self.timeout          = float( kwargs.get('timeout', 1 ) )
        
        self.socket = None
    
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
    
    def get_ack(self, message):
        hdr, data = self.get_single_message()
        if hdr.async_type == 'ACK':
            return True
        elif hdr.async_type == 'NACK':
            raise STKNackError(f'NACK Received: stk.send("{message}")')
    
    def report(self, ObjPath, Style, TimePeriod=None, TimeStep=None, AccessObjectPath=None, AdditionalData=None, Summary=None, AllLines=None):
        message = f'ReportCreate */{ObjPath} Style "{Style}"'
        if AccessObjectPath is not None: message += f' AccessObject {AccessObjectPath}'
        if TimePeriod       is not None: message += f' TimePeriod {TimePeriod}'
        if TimeStep         is not None: message += f' TimeStep {TimeStep}'
        if AdditionalData   is not None: message += f' AdditionalData "{AdditionalData}"'
        if Summary          is not None: message += f' Summary {Summary}'
        if AllLines         is not None: message += f' AllLines {AllLines}'
        
        self.send(message)
    
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
