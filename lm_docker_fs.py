#!usr/bin
#encoding: utf-8

"""A Docker image is built up from a series of layers. 
When create a new container, need to add a new writable layer on top of the underflying layes.
So the full system docker live migration need to migrate the file system.

lm_docker_filesystem: the class do all the filesystem operations.
	__init__: do some assignment ops.

	tar_file_without_path: tar directory, but do not store full paths in the archive

	workdir: store the file dir in /var/lib/docker/tmp/$task_id

	extract_file_to_path: extract file from the input tar dir

	tar_file: use tar_file_without_path function, tar /var/lib/docker/aufs/diff/$container-id in container.tar
			  tar /var/lib/docker/aufs/diff/$container-id+'-init' in container-init.tar
			  package the two tar file in fs.tar

	sync_file: we limit the container file ops in /home dir, after the last dump op, wo sync this dir to dst node.
	
	extract_sync: extract the sync dir in dst node.

	extract_file: extract the fs tar dir in dst node.

"""

import tarfile
import shutil
import logging
import time
from lm_docker_util import *


class lm_docker_filesystem:
	def __init__(self,container_id,task_id):
		self.container_id = container_id
		self.task_id = task_id
		self.fs_tar_name = task_id +'-fs.tar'
		self.sync_tar_name = task_id +'-sync.tar'
		self.container_tar = 'container.tar'
		self.container_init_tar = 'container-init.tar'
#		self.bind_tar = 'bind.tar'
		self.mount_tar = 'mount.tar'

	def tar_file_without_path(self,container_tar,path):
		os.chdir(path)
		logging.debug('tar path %s' %path)
		tar_file = tarfile.TarFile.open(container_tar,'w')
		tar_file.add('./')
		tar_file.close()
		shutil.move(container_tar,self.workdir())
		os.chdir('../')
		sp.call('pwd',shell=True)

	def workdir(self):
		return base_dir +'/tmp/' +self.task_id +'/'

	def image_path(self):
		return self.workdir() + '/' + self.fs_tar_name

	def sync_path(self):
		return self.workdir() + '/' + self.sync_tar_name
	
	def extract_file_to_path(self,tar,path):
		tar_file = tarfile.TarFile.open(tar,'r')
		tar_file.extractall(path)
		tar_file.close()
		os.remove(tar)

	def tar_file(self):
		if not os.path.isdir(self.workdir()):
			os.mkdir(self.workdir())
		layer_dir = base_dir + '/aufs/diff/'
		
		'''tar file in /$(container-id)/'''
		container_path = layer_dir + self.container_id
		if not check_dir(container_path):
			logging.error('Error: file path %s not exists' %container_path)
			return False
		container_tar = self.container_tar
		self.tar_file_without_path(container_tar,container_path)

		'''tar file in /$(container-id)-init/'''
		container_init_path = container_path +'-init'
		if not check_dir(container_init_path):
			logging.error('Error: init file path %s not exists' %container_init_path)
			return False
		container_init_tar = self.container_init_tar
		self.tar_file_without_path(container_init_tar,container_init_path)

		'''tar file in fs.tar'''
		os.chdir(self.workdir())
		if not (check_file(container_tar) and check_file(container_init_tar)):
			logging.error('Error:extract file system layer failed.')
			return False
		fs_tar_name = self.fs_tar_name
		fs_tar_file = tarfile.TarFile.open(fs_tar_name,'w')
		fs_tar_file.add(container_tar)
		fs_tar_file.add(container_init_tar)
		fs_tar_file.close()

		if not check_file(fs_tar_name):
			logging.error('Error: extract filesystem layer failed.')
			return False

		os.remove(container_tar)
		os.remove(container_init_tar)
		return True

	def sync_file(self):
		mount_dir = base_dir + '/aufs/mnt/'
		mount_path = mount_dir + self.container_id + '/home'
		if not check_dir(mount_path):
			logging.error('Error: file path is %s not exists' %mount_path)
			return False
		mount_tar = self.mount_tar
		tar = tarfile.open(mount_tar,'w')
		logging.info('sync tar start time is %s' %time.time())
		for root,dirs,files in os.walk(mount_path):
			for file in files:
				fullpath = os.path.join(root,file)
				relpath = os.path.relpath(fullpath,mount_path)
				tar.add(fullpath,arcname=relpath)
		tar.close()
		logging.info('sync tar end time is %s' %time.time())
		os.chdir(self.workdir())
		if not (check_file(mount_tar)):
			logging.error('Error:sync file system failed.')
			return False
		sync_tar_name = self.sync_tar_name
		sync_tar_file = tarfile.TarFile.open(sync_tar_name,'w')
		sync_tar_file.add(mount_tar)
		sync_tar_file.close()
		if not check_file(sync_tar_name):
			logging.error('Error: extract filesystem layer failed.')
			return False
		return True
	
	def extract_sync(self):
		os.chdir(self.workdir())
		sync_tar_name = self.sync_tar_name
		if not check_file(sync_tar_name):
			logging.error('Error: filesystem %s not exists.' %sync_tar_name)
			return False
		logging.info('sync untar start time is %s' %time.time())
		sync_tar_file = tarfile.TarFile.open(sync_tar_name,'r')

		logging.info('sync untar end time is %s' %time.time())
		sync_tar_file.extractall()
		sync_tar_file.close()
		mount_tar = self.mount_tar

		'''extract file into /var/lib/docker/aufs/mnt/$(container-id)/'''
		mount_path = base_dir + '/aufs/diff/' + self.container_id +'/home'
		if not check_dir(mount_path):
			logging.error('Error: dir %s is not exists.' %mount_path)
			return False
		self.extract_file_to_path(mount_tar,mount_path)
		
		return True


	def extract_file(self):

		'''extract file from fs.tar.gz'''
		os.chdir(self.workdir())
		fs_tar_name = self.fs_tar_name
		if not check_file(fs_tar_name):
			logging.error('Error: filesystem %s not exists.' %fs_tar_name)
			return False

		fs_tar_file = tarfile.TarFile.open(fs_tar_name,'r')
		fs_tar_file.extractall()
		fs_tar_file.close()

		container_tar = self.container_tar
		container_init_tar = self.container_init_tar
		if not (check_file(container_tar) and check_file(container_init_tar)):
			logging.error('Error: filesystem extract file failed, fs not exists.')
			return False

		'''extract file into /$(container-id)/'''
		container_path = base_dir + '/aufs/diff/' + self.container_id
		if not check_dir(container_path):
			logging.error('Error: dir %s is not exists.' %container_path)
			return False
		self.extract_file_to_path(container_tar,container_path)

		'''extract file into /$(container-id)-init/'''
		container_init_path = container_path + '-init'
		if not check_dir(container_init_path):
			logging.error('Error: dir %s is not exists.' %container_init_path)
			return False
		self.extract_file_to_path(container_init_tar,container_init_path)
		
		return True



