#!usr/bin
#encoding: utf-8

"""the global variable and functions."""

import random
import string
import os.path
import logging
import subprocess as sp

base_dir = '/var/lib/docker'
PORT = 10019
cgroup_log = '/var/lib/docker/cgroup.log'
mount_log = '/var/lib/docker/mount.log'
inetsk_log = '/var/lib/docker/inetsk.log'
crit_bin = '/home/hdq/criu/crit/crit'
cgroup_img = '/cgroup.img'
mount_img = '/mountpoints-12.img'
inetsk_img = '/inetsk.img'

#----decide whether the string is blank or not.----#
def isBlank(inString):
	if inString and inString.strip():
		return False
	return True

#----check whether the directory is exist or not----#
def check_dir(file_path):
	if os.path.exists(file_path):
		return True
	else:
		return False

#----check whether the file is exist or not----#
def check_file(file):
	if os.path.isfile(file):
		return True
	else:
		return False

#----produce the random string to be the tmp directory name, aka task_id----#
def random_str(size = 6,chars = string.ascii_lowercase + string.digits):
	return ''.join(random.choice(chars) for _ in range(size))
