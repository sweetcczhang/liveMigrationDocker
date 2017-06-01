#!/usr/bin
#encoding: utf-8

"""start server in dst node"""

import os
import netifaces as ni
import logging
import SocketServer
import time

from lm_docker_util import *
from lm_docker_server import lm_docker_server

class ServerThread(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
	pass


class server_node:
	def run(self):
		HOST = ni.ifaddresses('p1p1')[2][0]['addr']
		logging.info(HOST)
		server = ServerThread((HOST,PORT),lm_docker_server)
		try:
			server.serve_forever()
		except KeyboardInterrupt:
			logging.debug('server node stop because of keyboard interrupt')
			server.shutdown()
		server.server_close()
