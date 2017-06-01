#!usr/bin
#encoding: utf-8

"""do the checkpoint ops.

lz4_tarfile: use lz4 algorithm to compress all the *.pages files.

lm_docker_memory: the class include predump and dump func.
	
	__init__: do some initialization

	workdir: /var/lib/docker/tmp/$task_id/

	predump_name: get the predump dir

	predump_image_path: this predump image with full path

	dump_image_path: dump image with full path

	predump: do the predump checkpoint op, after this container still running.

	tar_image: tar the checkpoint files to *.tar with lz4

	dump: do the dump checkpoint op, after this container status is checkpointed.

"""
import os
import shutil
import tarfile
import time

from lm_docker_util import *
from lm_docker_check import lm_docker_check

#----use lz4 algorithm to compress the *.pages file.----#
def lz4_tarfile(level,input_dir='./'):
	for root, subFolders, files in os.walk(input_dir):
		for f in files:
			if f.find('pages') != -1:
				input_name = f
				output_name = input_name + '.lz4'
				cmd = 'lz4 -' + level + ' ' + input_name + ' ' + output_name
				logging.debug(cmd)
				sp.call(cmd,shell=True)
				os.remove(input_name)

#----this class do the two type checkpoint operate.----#		
class lm_docker_memory:
	def __init__(self, task_id):
		self.task_id = task_id
		self.predump_count = 0
		os.chdir(self.workdir())

	def workdir(self):
		return base_dir + '/tmp/' +self.task_id + '/'

	def predump_name(self):
		return 'predump' + str(self.predump_count)

	def predump_image_path(self):
		return self.workdir() + self.task_id + '-' +self.predump_name() +'.tar'

	def dump_image_path(self):
		return self.workdir() + self.task_id + '-dump.tar'
	
	#----change the last predump dir name to 'predump'----#
	def rename(self):
		os.rename(self.predump_name(),'predump')

	'''predump checkpoint used in pre-copy loop, get the memory info.
	   we use predump function to decrease the halt time.
	   in each iterative, we need the image_dir and parent_dir info.
	   flag 'is_transfer' means whether last predump info is transfer or not, 
	   if not image_dir and parent_dir is same as last predump, else use new ones.
 	'''
	def predump(self,container_id,is_transfer):
		os.chdir(self.workdir())
		if(is_transfer == True):
			self.predump_count += 1
		dir_name = self.predump_name()
		if(is_transfer == False):
			shutil.rmtree(dir_name)
		dir_path = self.workdir() + dir_name
		work_path = self.workdir()
		os.mkdir(dir_name)

		if self.predump_count > 1:
			parent_dir = 'predump' + str(self.predump_count - 1)
			if not check_dir(self.workdir() + parent_dir):
				logging.error('Error: parent dir is not exists.')
			parent_path = '../'  + parent_dir
			append_cmd = '--prev-images-dir=' + parent_path
		else:
			append_cmd = ''
		predump_sh = 'docker checkpoint --image-dir=' + dir_path +\
                     ' --work-dir=' + work_path +\
					 ' --pre-dump --allow-shell=true --allow-tcp=true --leave-running ' +\
					 append_cmd + ' ' + container_id
		logging.debug(predump_sh)
		
		out_msg = sp.call(predump_sh, shell=True)
		if out_msg:
			logging.error('Error: criu pre-dump failed.')
			return False
		name = self.task_id + '-' + dir_name +'.tar'
		self.tar_image(self.workdir(),name,dir_name)
		return True

	def tar_image(self,image_dir,name,path):
		os.chdir(image_dir)
		os.chdir(path)
		lz4_tarfile('1')
		os.chdir(image_dir)
		tar_file = tarfile.open(name,'w')
		tar_file.add(path)
		tar_file.close()
		if not check_file(name):
			logging.error('Error: package failed.')
			return False
		return True

	'''dump checkpoint op used in last dump step,
	   get the last dirty pages and running states.
	'''
	def dump(self,pid,container_id):
		os.chdir(self.workdir())
		dump_time_start = time.time()
		logging.debug('dump the docker init process ' + str(pid))
		dump_dir = 'dump'
		predump_dir = 'predump'
		os.mkdir(dump_dir)
		dump_path = self.workdir() + dump_dir
		work_path = self.workdir()
		parent_path = '../' + predump_dir
		dump_sh = 'docker checkpoint --image-dir=' + dump_path +\
                          ' --work-dir=' + work_path +\
                          ' --track-mem --allow-shell=true --allow-tcp=true --prev-images-dir=' +\
						  parent_path + ' ' + container_id
		
		out_msg = sp.call(dump_sh, shell=True)
		logging.info('container stop time is ' + str(time.time()))
		if out_msg:
			logging.error('Error: criu dump failed')
			return False
		name = self.task_id + '-' + dump_dir +'.tar'
		self.tar_image(self.workdir(),name,dump_dir)
		logging.info('dump image tar end time is %s :' %time.time()) 
		return True

