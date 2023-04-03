#!/usr/bin/env python
from http.server import BaseHTTPRequestHandler, HTTPServer
import ssl
import socket, select
from urllib import parse as urllib_parse
import argparse
import base64

KEYFILE = "tun.key"
CERTFILE = "tun.crt"
key = ''

class ProxyRequestHandler(BaseHTTPRequestHandler):

    sockets = {}
    BUFFER = 1024 * 50 
    SOCKET_TIMEOUT = 50

    def _get_connection_id(self):
        return self.path.split('/')[-1]

    def _get_socket(self):
        """get the socket which connects to the target address for this connection"""
        id = self._get_connection_id()
        return self.sockets.get(id, None)

    def _close_socket(self):
        """ close the current socket"""
        id = self._get_connection_id()
        s = self.sockets[id]
        if s:
            s.close()
            del self.sockets[id]
    
    def do_AUTHHEAD(self):
        print("Send Auth Header")
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm=\"Test\"')
        self.send_header('Content-type', 'text/html')
        self.end_headers()
    
    def do_GET(self):
        global key
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()
            self.wfile.write(b'no auth header received')
            pass
        elif self.headers.get('Authorization') == 'Basic '+key:
            """GET: Read data from TargetAddress and return to client through http response"""
            s = self._get_socket()
            if s:
                # check if the socket is ready to be read
                to_reads, to_writes, in_errors = select.select([s], [], [], 5)
                if len(to_reads) > 0: 
                    to_read_socket = to_reads[0]
                    try:
                        print("Getting data from target address")
                        data = to_read_socket.recv(self.BUFFER)
                        print(data)
                        self.send_response(200)
                        self.end_headers()
                        if data:
                            data = base64.b64encode(data)
                            self.wfile.write(data)
                    except socket.error as ex:
                        print('Error getting data from target socket: %s' % ex)  
                        self.send_response(503)
                        self.end_headers()
                else: 
                    print('No content available from socket')
                    self.send_response(204) # no content had be retrieved
                    self.end_headers()
            else:
                print('Connection With ID %s has not been established' % self._get_connection_id())
                self.send_response(400)
                self.end_headers()
        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.get('Authorization'))
            self.wfile.write(b'not authenticated')
            pass

    def do_POST(self):
        global key
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()
            self.wfile.write(b'no auth header received')
            pass
        elif self.headers.get('Authorization') == 'Basic '+key:
            """POST: Create TCP Connection to the TargetAddress"""
            id = self._get_connection_id() 
            print('Initializing connection with ID %s' % id)
            length = int(self.headers.get('content-length'))
            req_data = self.rfile.read(length)
            params = urllib_parse.parse_qs(req_data, keep_blank_values=1) 
            print(params)
            target_host = params[b'host'][0].decode("utf-8")
            target_port = int(params[b'port'][0])

            print('Connecting to target address: %s % s' % (target_host, target_port))
            # open socket connection to remote server
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # use non-blocking socket
            s.setblocking(0)
            s.connect_ex((target_host, target_port))

            #save socket reference
            self.sockets[id] = s
            try: 
                self.send_response(200)
                self.end_headers()
            except socket.error as e:
                print(e)
        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.get('Authorization'))
            self.wfile.write(b'not authenticated')
            pass
    
    def do_PUT(self):
        global key
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()
            self.wfile.write(b'no auth header received')
            pass
        elif self.headers.get('Authorization') == 'Basic '+key:
            """Read data from HTTP Request and send to TargetAddress"""
            id = self._get_connection_id()
            s = self.sockets[id]
            if not s:
                print("Connection with id %s doesn't exist" % id)
                self.send_response(400)
                self.end_headers()
                return
            length = int(self.headers.get('content-length'))
            data = urllib_parse.parse_qs(self.rfile.read(length), keep_blank_values=1)[b'data'][0] 
            data = base64.b64decode(data)

            # check if the socket is ready to write
            to_reads, to_writes, in_errors = select.select([], [s], [], 5)
            if len(to_writes) > 0: 
                print('Sending data .... %s' % data)
                to_write_socket = to_writes[0]
                try: 
                    to_write_socket.sendall(data)
                    self.send_response(200)
                except socket.error as ex:
                    print('Error sending data from target socket: %s' % ex)
                    self.send_response(503)
            else:
                print('Socket is not ready to write')
                self.send_response(504)
            self.end_headers()
        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.get('Authorization'))
            self.wfile.write(b'not authenticated')
            pass
    
    def do_DELETE(self): 
        global key
        if self.headers.get('Authorization') == None:
            self.do_AUTHHEAD()
            self.wfile.write(b'no auth header received')
            pass
        elif self.headers.get('Authorization') == 'Basic '+key:
            self._close_socket()
            self.send_response(200)
            self.end_headers()
        else:
            self.do_AUTHHEAD()
            self.wfile.write(self.headers.get('Authorization'))
            self.wfile.write(b'not authenticated')
            pass

def run_server(port, server_class=HTTPServer, handler_class=ProxyRequestHandler): 
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    httpd.socket = ssl.wrap_socket (httpd.socket, keyfile=KEYFILE, certfile=CERTFILE, server_side=True)
    httpd.serve_forever()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Start Tunnel Server")
    parser.add_argument("-p", default=8443, dest='port', help='Specify port number server will listen to', type=int)
    args = parser.parse_args()
    key = base64.b64encode(b'***:***').decode('ascii')
    run_server(args.port)
