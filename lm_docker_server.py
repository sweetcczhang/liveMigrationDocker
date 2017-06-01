#!/usr/bin
#encoding: utf-8

"""lm_docker server running in dst node, handle with the recv msg and files.

lm_docker_server: request handler in dst node.
	recv_file: receive the files which send from src node.
	send_msg: send msg to client(aka src node).
	recv_msg: receive msg.
	handle: implement communication with the client
"""
import os
import netifaces as ni
import logging
import SocketServer
import struct
import time

from lm_docker_util import *
from lm_docker_dstnode import destination_node

BUF_SIZE = 1024

#---the request handler class for server, it is instantiated once per connection to the server----#
class lm_docker_server(SocketServer.BaseRequestHandler):
	def recv_file(self,file_name,file_size):
		hd_file = open(file_name,'wb')
		try:
			buffer = b''
			length = file_size
			while(length > 0):
				tmp = self.request.recv(length)
				if not tmp:
					return False
				buffer = buffer + tmp
				length = file_size - len(buffer)

			hd_file.write(buffer)
			hd_file.close()
			return True
		except Exception as conError:
			logging.error('Error: connection error, conError:%s' %conError)
	
	def send_msg(self,msg):
		length = len(msg)
		self.request.send(struct.pack('!I',length))
		self.request.send(msg)

	def recv_msg(self):
		format_buf = self.request.recv(4)
		length, = struct.unpack('!I',format_buf)
		return self.request.recv(length)

	#----override handler method to implement conmmunication with client.----#
	def handle(self):
		tmp = self.recv_msg()
		logging.debug ('tmp:' + tmp)
		str_array = tmp.split('#')
		dst_handle = destination_node()
		cmd_type = str_array[0]

		#----if the msg is init#...,call init_dst_node to create a new container----#
		if 'init' == cmd_type:
			self.task_id = str_array[1]
			self.label = str_array[2]
			dst_handle.init_dst_node(self.task_id,self.label)
			self.send_msg('init:success')
			logging.info('get init msg success.')
	
		#----keep listening to recv msg or file from src node.----#
		while(True):
			'''client always send a msg before send files
			   use this msg to distinguish files type. 
			'''
			new_msg = self.recv_msg()
			logging.debug(new_msg)
			str_array = new_msg.split('#')
			cmd_type = str_array[0]
			
			'''if the msg beginning is fs,it means we next will recv filesystem.
			   after recv files, call dst_filesystem to recover the filesystem.
			'''
			if 'fs' == cmd_type:
				fs_time_start = time.time()
				fs_image = self.task_id + '-fs.tar'
				fs_size = int (str_array[1])
				msg_fs = 'fs:'
				if self.recv_file(fs_image,fs_size):
					msg_fs += 'success'
				else:
					msg_fs += 'failed'
				self.send_msg(msg_fs)
				dst_handle.dst_filesystem()
				fs_time_end = time.time()
			
			'''if the beginning is sync, means we next recv is sync filesystem.
			   after recv files, call sync_filesystem to sync the filesystem.
			'''
			if 'sync' == cmd_type:
				sync_time_start = time.time()
				sync_image = self.task_id + '-sync.tar'
				sync_size = int(str_array[1])
				msg_sync = 'sync:'
				if self.recv_file(sync_image,sync_size):
					msg_sync += 'success'
				else:
					msg_sync += 'failed'
				self.send_msg(msg_sync)
				dst_handle.sync_filesystem()
				sync_time_end = time.time()
			
			'''if the beginning is predump, after recv files,
			   call predump_restore to extract predump checkpoint files.
			'''
			if 'predump' == cmd_type:
				predump_time_start = time.time()
				predump_image = self.task_id + str_array[1] +'.tar'
				logging.debug(predump_image)
				predump_size = int(str_array[2])
				logging.info('predump size is : %s ' %predump_size)
				msg_predump = 'predump:'
				if self.recv_file(predump_image,predump_size):
					msg_predump += 'success'
				else:
					msg_predump += 'failed'
				self.send_msg(msg_predump)
				logging.debug(msg_predump)
				dst_handle.predump_restore(predump_image,str_array[1])
				predump_time_end = time.time()
			
			'''if the beginning is dump, after recv files,
			   restore the container in dst node.
			'''	 
			if 'dump' == cmd_type:
				dump_time_start = time.time()
				dump_image = self.task_id + '-mm.tar'
				dump_size = int(str_array[1])
				last_predump_dir = str_array[2]
				dump_pid = str_array[3]
				last_container_id = str_array[4]
				src_ip = str_array[5]
				dst_ip = str_array[6]
				logging.info('last dump size is : %s' %dump_size) 

				if last_predump_dir != 'predump0':
					os.rename(last_predump_dir, 'predump')
				msg_dump = 'dump:'
				if self.recv_file(dump_image,dump_size):
					msg_dump += 'success'
				else:
					msg_dump += 'failed'
				self.send_msg(msg_dump)
				logging.debug(msg_dump)
				dst_handle.restore(dump_pid,dump_image,last_container_id,src_ip,dst_ip)
				dump_time_end = time.time()
				self.send_msg('restore:success')
				logging.info('send restore success msg time is %s :' %time.time())
				break



