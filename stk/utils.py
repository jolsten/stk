# -*- coding: utf-8 -*-
"""
Created on Wed Aug  5 07:27:15 2020

@author: jolsten
"""

STK_DATEFMT = '%d %b %Y %H:%M:%S.%f'


from inspect import getmembers, isfunction

def inherit_docstrings(cls):
    for name, func in getmembers(cls, isfunction):
        if func.__doc__: continue
        for parent in cls.__mro__[1:]:
            if hasattr(parent, name):
                func.__doc__ = getattr(parent, name).__doc__
    return cls