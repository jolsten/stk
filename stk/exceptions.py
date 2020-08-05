# -*- coding: utf-8 -*-
"""
Created on Tue Aug  4 20:13:16 2020

@author: jolst
"""

import logging

class STKLicenseError(RuntimeError):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None

    def __str__(self):
        if self.message:
            return f'{type(self).__name__}: {self.message}'
        else:
            return f'{type(self).__name__} has been raised'


class STKConnectError(RuntimeError):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None
    
    def __str__(self):
        if self.message:
            return f'{type(self).__name__}: {self.message}'
        else:
            return f'{type(self).__name__} has been raised'


class STKNackError(IOError):
    def __init__(self, *args):
        if args:
            self.message = args[0]
        else:
            self.message = None
    
    def __str__(self):
        if self.message:
            return f'{type(self).__name__}: {self.message}'
        else:
            return f'{type(self).__name__} has been raised'
