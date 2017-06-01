#!/usr/bin
#encoding: utf-8

"""This file do the live migration.

get_container_info: get some container information
	Args:container_name
	Return: container_id,label,container pid

check_container_status: check whether the container is running or not.

sizeof_format: calculate the image file size.

live_migrate: the class is the main feature, do live migration.
	__init__: do some initial assignment.

	run: main function, do the migrate ops.

"""

import socket
import struct
import logging
import time

from docker import Client
from lm_docker_util import *
from lm_docker_client import lm_docker_socket
from lm_docker_fs import lm_docker_filesystem
from lm_docker_mem import lm_docker_memory
BUF_SIZE = 1024


#----Get the container information by the container name. (id,label,pid)----#
def get_container_info(container_name):
	cli = Client(version='1.21')
	out = cli.inspect_container(container_name)
	
	if 'Error' in out:
		logging.error('Error: Get container id Failed')
		return None,None

	image = out['Config']['Image']
	image_id = out['Image']
	label = container_name + '-' + image + '-' + image_id
	logging.info(label)
	pid = out['State']['Pid']
	logging.info(pid)

	return out['Id'],label,pid


#----Check whether the container is running or not.----#
def check_container_status(container_id):
	cli = Client(version='1.21')
	out = cli.containers(container_id)
	lines = str(out)

	if 'Id' in lines:
		logging.info('container id is get by docker-py:%s' %out[0]['Id'])
		return True
	return False


#----format the image file size----#
def sizeof_format(num,suffix = 'B'):
	for unit in ['','Ki','Mi','Gi','Ti','Pi','Ei','Zi']:
		if abs(num) < 1024.0:
			return '%3.1f%s%s' %(num,unit,suffix)
		num /= 1024.0
	return '%.1f%s%s' %(num,unit,suffix)



#----The main feature, live migration ----#
class live_migrate:
	def __init__(self, container_name, dst_ip):
		self.dst_ip = dst_ip
		self.container_name = container_name
		self.task_id = random_str()
		self.container_id, self.label, self.pid = get_container_info(container_name)

	"""do the migrate operate.
	
	Step1: check the container is running or not, and check the dst node environment.

	Step2: send the init message to dst.
		   according to the information do docker create op in dst node.
	
	Step3: send the fs.tar to dst and wait for the ack message. 
	       at the same time, dst recv msg and do some init op().

	Step4: implement pre-copy loop to synchronize the memory info.

	Step5: do the last dump step, migrate last dirty memory and running state.

	"""
	def run(self):
		start_time = time.time()
		logging.info('migrate start time : %s' %start_time)

		#----check container status: ensure the container is running in src.----# 
		if not check_container_status(self.container_id):
			logging.error('Error: Container which you want to migrate is not running.')
			return False

		#----send the init message to dst node. include task_id and base image----#
		lm_socket = lm_docker_socket(self.dst_ip)
		msg = 'init#' + self.task_id + '#' + self.label
		logging.debug('client send msg: %s ' %msg)
		lm_socket.send_msg(msg)
		data = lm_socket.recv_msg()
		logging.debug('client recv msg: %s' %data)
		if 'success' not in data:
			logging.error('send msg failed')
			return False
	
		#----send the file system to dst node.----#
		fs_handle = lm_docker_filesystem(self.container_id,self.task_id)
		if not fs_handle.tar_file():
			logging.error('Error: tar file failed\n')
			return False
		fs_image = fs_handle.image_path()
		msg_fs = 'fs#' + str(os.path.getsize(fs_image)) + '#'
		logging.debug(msg_fs)
		lm_socket.send_msg(msg_fs)
		lm_socket.send_file(fs_image)
		data = lm_socket.recv_msg()
		logging.debug(data)

		#----start the pre-copy looper, use pre-copy to decrease the halt time.----#
		pre_time_start = time.time()
		livemigrate_handle = lm_docker_memory(self.task_id)
		flag_precopy = True
		count = 1
		last_trans_time = 0
		last_dirty_size = 0
		is_transfer = True

		'''first use docker checkpoint --pre-dump to dump all the memory pages;
		   then in each loop use docker checkpoint --pre-dump --TRACK-MEM to dump the dirty pages.
		'''
		while(flag_precopy):
			'''in each loop, first do the predump op.
			   input args 'is_transfer' means whether the last predump info is transfer or not. '''
			if not livemigrate_handle.predump(self.container_id,is_transfer):
				return False
			predump_image = livemigrate_handle.predump_image_path()
			predump_size = os.path.getsize(predump_image)

            '''if the first predump, send the dump files.
			   assignment the last_trans_time,last_dirty_size, and let is_transfer=True'''
			if(count == 1):
				msg_predump = 'predump#' + livemigrate_handle.predump_name() + \
							  '#' + str(predump_size) + '#'
				logging.debug(msg_predump)
				lm_socket.send_msg(msg_predump)
				send_predump_image_start = time.time()
				lm_socket.send_file(predump_image)
				data = lm_socket.recv_msg()
				send_predump_image_end = time.time()
				count+=1
				last_trans_time = send_predump_image_end - send_predump_image_start
				last_dirty_size = predump_size
				is_transfer = True
#				logging.info('predump image size is : %s ' %sizeof_format(predump_size))
#				logging.info('measure bandwidth is : %s /s' %sizeof_format((predump_size*8)/(send_predump_image_time)))

			'''if count equals the MAX_LOOP, send the dump files and stop the loop.'''
			elif(count == 30):	
			    '''send the predump files to the dst node'''
				msg_predump = 'predump#' + livemigrate_handle.predump_name() + \
							  '#' + str(predump_size) + '#'
				logging.debug(msg_predump)
				lm_socket.send_msg(msg_predump)
				send_predump_image_start = time.time()
				lm_socket.send_file(predump_image)
				data = lm_socket.recv_msg()
				send_predump_image_end = time.time()
				send_predump_image_time = send_predump_image_end - send_predump_image_start
				logging.debug('predump image size is : %s ' %sizeof_format(predump_size))
				logging.debug('measure bandwidth is : %s /s' %sizeof_format((predump_size*8)/(send_predump_image_time)))
				flag_precopy = False
				logging.info('predump loop end.')
				livemigrate_handle.rename()
			
			'''if the dirty ratio is too large, we do not tranfer this predump files.'''
#			elif(predump_size >= last_dirty_size*0.95 and is_transfer):
#				count+=1
#				is_transfer = False
			else:
				'''send the predump files to the dst node'''
				msg_predump = 'predump#' + livemigrate_handle.predump_name() + \
								'#' + str(predump_size) + '#'
				logging.debug(msg_predump)
				lm_socket.send_msg(msg_predump)
				send_predump_image_start = time.time()
				lm_socket.send_file(predump_image)
				data = lm_socket.recv_msg()
				send_predump_image_end = time.time()
				last_dirty_size = predump_size
				last_trans_time = send_predump_image_end - send_predump_image_start
				logging.debug('predump image size is : %s ' %sizeof_format(predump_size))
				logging.debug('measure bandwidth is : %s /s' %sizeof_format((predump_size*8)/(last_trans_time)))
				count+=1
				is_transfer = True
				'''if the dirty pages < threshold, stop the pre-copy loop.'''
				if((predump_size/last_dirty_size)*last_trans_time <= 0.03):
					flag_precopy = False
		
		'''do the last step,dump the change memory and running states
		   send the dump image for dst node to restore the docker container.'''
		logging.info('dump step start time is %s :' %time.time())
		if not livemigrate_handle.dump(self.pid,self.container_id):
			logging.error('Error: there is something wrong in the last dump step.')
			return False
		dump_image = livemigrate_handle.dump_image_path()
		dump_size = os.path.getsize(dump_image)

		'''
		send the sync file to the destination
		'''
#		sync_handle = lm_docker_filesystem(self.container_id,self.task_id)
#		if not sync_handle.sync_file():
#			logging.error('Error: sync file failed.')
#			return False
#		sync_image = sync_handle.sync_path()
#		msg_sync = 'sync#' + str(os.path.getsize(sync_image)) +'#'
#		logging.debug(msg_sync)
#		lm_socket.send_msg(msg_sync)
#		lm_socket.send_file(sync_image)
#		data = lm_socket.recv_msg()
#		logging.debug(data)

		#----send the dump image to the dst node----#
		msg_dump = 'dump#' + str(dump_size) +'#' +\
				   livemigrate_handle.predump_name() +'#' +\
                   str(self.pid) +'#'+\
				   self.container_id +'#'
		lm_socket.send_msg(msg_dump)
		logging.info('dump image send img start time id %s :' %time.time())
		lm_socket.send_file(dump_image)
		logging.info('dump image send success time is %s :' %time.time())
		logging.debug('dump image size is : %s ' %sizeof_format(dump_size))
		logging.debug('measure bandwidth is : %s /s' %sizeof_format((dump_size *8)/(send_dump_image_time)))
		data = lm_socket.recv_msg()
		logging.info('dump step source node receive msg time is %s :' %time.time())

		return True

