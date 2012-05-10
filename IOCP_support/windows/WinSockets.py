"""
This file is used only to  patching the builtin sockets library
on windows to support iocp.
you just need to import that, and not to call nothing of this content

@author Marcelo Aires Caetano
@email <marcelo at fiveti dot com>
@date 2012 may 10

"""
"""
Copyright (c) 2012 caetano

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

__all__ = []
import sys 

assert 'win32' in sys.platform
from types import MethodType

from socket import * 

from .winfile_api import AllocateBuffer, OVERLAPPED, AcceptEx, SO_UPDATE_ACCEPT_CONTEXT


import struct


def using_iocp(self):
    return self._winsocket.using_iocp


def _winsocket(self):
    """
    runtime selfpatching
    """
    try:
        self.recvfrom_into.using_iocp
    except:
        """
        not registered inside object _winsocket yet.
        """
        __name__ = self.recvfrom_into.__name__
        __doc__ = self.recvfrom_into.__doc__
        self.recvfrom_into = _Winsock(self)
        self.recvfrom_into.__name__ = __name__
        self.recvfrom_into.__doc__ = __doc__
        
    return self.recvfrom_into

socket.using_iocp = property(using_iocp)
socket._winsocket = property(_winsocket)
socket._sock_recv = socket.recv
socket._sock_accept = socket.accept

class _Winsock(object):
    __slots__ = ['using_iocp', 'iocp', 'listening', 'listening_n', 'acceptors',
                 'MAX_CACHED_SOCKETS', 'socket', 'max_cached_sockets_n']
    def __init__(self, socket):
        self.MAX_CACHED_SOCKETS = [128] #max number of pre-accepted sockets
        self.max_cached_sockets_n = 0 
        self.using_iocp = False
        self.listening = False
        self.listening_n = 0
        self.acceptors = []
        self.iocp = None
        self.socket = socket
        
    def __call__(self, self_socket, *args, **kw):
        return self_socket._sock.recvfrom_into(*args, **kw)
    
    def perform_accept_ex_addrs(self):
        s1, buf = self.acceptors.pop(0)
        s1.setsockopt(
            socket.SOL_SOCKET,
            SO_UPDATE_ACCEPT_CONTEXT,
            struct.pack("I", self.socket.fileno())
        )
        #TODO
        #GetAcceptExSockaddrs(self.socket, buff)
        
        #checking if the cache is null, if, repopulate cache
        self.perform_accept_ex()
        return (s1, s1.getpeername())

    
    def perform_accept_ex(self):
        """
        maintain a cache of preallocated sockets for faster accepting sockets
        """
        
        if not self.max_cached_sockets_n:
            if self.listening_n > self.MAX_CACHED_SOCKETS[0]:
                self.max_cached_sockets_n = self.MAX_CACHED_SOCKETS[0]
            else:
                self.max_cached_sockets_n = self.listening_n
        if not self.acceptors:      
            while len(self.acceptors) < self.max_cached_sockets_n:
                
                buff = AllocateBuffer(64)
                overlapped = OVERLAPPED()
                s1 = socket.socket()
                AcceptEx(self.socket, s1, buff, overlapped)
                self.acceptors.append((s1,buff))
                
    def perform_wait_event(self):
        timeout = self.socket.gettimeout()
        self.iocp._wait_event(self.socket, timeout)
            

    def unregister_iocp(self):
        self.using_iocp = False
        self.iocp = None
        del self.acceptors
        self.acceptors = []
        

def accept(self):
    """
    Perform accept on a socket, because windows is a faggot!
    """
    if self.using_iocp:
        self._winsock.perform_wait_event()
        r = self._winsock.perform_accept_ex_addrs(self)
        return (ac, remoteaddr)
    else:
        return self._socket_accept()

def listen(self, value):
    self._winsock.listening = True
    self._winsock.listening_n = value
    r = self._listen(value)
    if self.using_iocp:
        self._winsock.perform_accept_ex(self)
    return r

def recv(self, value):
    if self.using_iocp:
        self._winsock.perform_wait_event()
    return self._sock_recv(value)


socket.accept = MethodType(accept, None, socket)
socket.listen = MethodType(listen, None, socket)
socket.recv = MethodType(recv, None, socket)