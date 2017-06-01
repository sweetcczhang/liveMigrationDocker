#!/usr/bin
#encoding: utf-8

"""live migration tool in the destination node, used to receive file and do the restore command.

lz4_extractfile:use lz4 algorithm to unzip the package.
	Args: file package.
	Returns: unzip file.

destination_node: This class used to execute all the command in the destination node.
	
	__init__: Jump to the /var/lib/docker/tmp directory,which we use to storage container info.

	init_dst_node: create a new container in destination node according to the base image.
		Args: 
			task_id: the migrate docker container uuid.  
			label: container_name + '-' + image + '-' + image_id 
		Returns:
			split the label to get label_array, then remove the container in dst node if it exists.
			use the base image create a new docker container, its status is created.

	dst_filesystem: call the lm_docker_filesystem.extract_file() to recover container filesystem.

	sync_filesystem: calll the lm_docker_filesystem.sync() to sync container filesystem.

	predump_restore: recover the predump directory.

	restore: execute the restore command to resume container running in dst node.
		Args:
			pid: the docker container pid in src node.(which used in external version, now is useless)
			dump_image_name: container info after execute last dump step.
			last_container_id: container id in src node.(which used in externalversion to do map ops)
			src_ip: container host ip in src node.
			dst_ip: container host ip in dst node. 
		Returns: 
			True if the container restore successful.
			Error if the container restore failed.
"""

import os
import logging
import shutil
import tarfile
import commands
import time
import socket
import struct

from lm_docker_util import *
from lm_docker_fs import lm_docker_filesystem
from lm_docker_mem import lm_docker_memory

def lz4_extractfile(input_dir = './'):
	for root, subFolders, files in os.walk(input_dir):
		for f in files:
			if f.find('.lz4') != -1:
				input_name = f
				length = len(f)
				output_name = f[0:length-4]
				cmd = 'lz4 -d ' + input_name + ' ' + output_name
				logging.info(cmd)
				sp.call(cmd,shell=True)
				os.remove(input_name)

class destination_node:
	#----init the class, jump to the docker dir.----#
	def __init__(self):
		os.chdir(base_dir + '/tmp/')

	#----get the extractly container dir.----#
	def workdir(self):
		return base_dir + '/tmp/' + self.task_id

	#----create a new container in dst node.----#
	def init_dst_node(self, task_id, label):
		if not os.path.isdir(task_id):
			os.mkdir(task_id)
		os.chdir(task_id)
		self.task_id = task_id

		'''parse the label info.'''
		label_array = label.split('-')
		container_name = label_array[0]
		base_image = label_array[1]
		image_id = label_array[2]
		logging.debug('The docker image id is %s' %image_id)
		logging.debug(label_array)

		'''create new docker container.'''	
		rmv_sh = 'docker rm -f ' + container_name +' >/dev/null 2>&1'
		logging.debug(rmv_sh)
		os.system(rmv_sh)
		cre_sh = 'docker create --name=' + container_name + ' ' + base_image
		logging.debug(cre_sh)
		ret,con_id = commands.getstatusoutput(cre_sh)
		self.container_id = con_id

	#----untar the last dump directory.----#
	def untar_image(self, image_name, dump_dir):
		os.chdir(self.workdir())
		if not check_file(image_name):
			logging.error('Error: file is not exists, maybe something wrong in receive from client.')
			return False
		tar_file = tarfile.open(image_name,'r')
		tar_file.extractall()
		tar_file.close()
		os.chdir(dump_dir)
		lz4_extractfile()
		os.chdir('../')
		return True

	#----restore the init filesystem.----#
	def dst_filesystem(self):
		dst_fs = lm_docker_filesystem(self.container_id, self.task_id)
		if dst_fs.extract_file() is False:
			logging.error('Error: filesystem in destination node restore failed.')
			return False
		return True

	#----the last sync filesystem.----#
	def sync_filesystem(self):
		dst_fs = lm_docker_filesystem(self.container_id,self.task_id)
		if dst_fs.extract_sync() is False:
			logging.error('Error: sync filesystem in destination node failed.')
			return False
		return True

	#----untar the predump directory.----#
	def predump_restore(self, predump_image_name, predump_dir):
		self.untar_image(predump_image_name, predump_dir)
	
	#----restore the docker container in dst node.----#
	def restore(self,pid,dump_image_name,last_container_id,src_ip,dst_ip):
		ready_time_start = time.time()
		logging.info('restore ready start is %s :' %ready_time_start)
		os.chdir(self.workdir())
		self.untar_image(dump_image_name,'dump')
		image_dir = self.workdir() +'/dump'
		parent_path = self.workdir() +'/predump'

		if(os.path.isFile(image_dir + inetsk_img)):
			'''do the map operate to the inetsk.img, change the TCP socket src_ip to dst_ip.'''
			decode_sh = 'sudo ' + crit_bin + ' decode -i ' + image_dir +\ 
			   inetsk_img + ' -o ' + inetsk_log
			p = sp.Popen(decode_sh,shell=True,stdin=sp.PIPE,stdout=sp.PIPE,stderr=sp.PIPE)
			p.stdin.write('123456\n')
			ret = p.wait()
			logging.debug(decode_sh)
			if ret:
				logging.error('Error: crit decode inetsk.img failed.')
				return False
			src_ip_num = struct.unpack("=I",socket.inet_aton(src_ip))[0]
			dst_ip_num = struct.unpack("=I",socket.inet_aton(dst_ip))[0]
			sed_sh = 'sudo sed -i \"s/' + bytes(src_ip_num) +'/' +bytes(dst_ip_num) +\
					 '/g\" ' +inetsk_log
			sp.call(sed_sh,shell=True)
			encode_sh = 'sudo ' + crit_bin + ' encode -i ' + inetsk_log +\
						' -o ' +image_dir + inetsk_img
			p = sp.Popen(encode_sh,shell=True,stdin=sp.PIPE,stdout=sp.PIPE,stderr=sp.PIPE)
			p.stdin.write('123456\n')
			ret = p.wait()
			logging.debug(encode_sh)
			if ret:
				logging.error('Error: crit decode inetsk.img failed.')
				return False

		restore_op = 'docker restore --force=true --allow-shell=true --allow-tcp=true' +\
					 ' --work-dir=' + image_dir +\
					 ' --image-dir=' + image_dir + ' ' + self.container_id
	    logging.debug(restore_op)
		ready_time_end = time.time()
		logging.info('restore ready time end is %s :' %ready_time_end)
		sp_call_start = time.time()
		ret = sp.call(restore_op,shell = True)
		sp_call_end = time.time()
		logging.info('restore start is %s :' %sp_call_start)
		logging.info('restore end is %s :' %sp_call_end)
		resume_time = time.time()
		logging.info('live migrate tools halt time is ' + str(resume_time))
		logging.info(ret)

		if 0 != ret:
			logging.error('docker restore failed.')
			return False
		return True



