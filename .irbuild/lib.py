#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import subprocess
import lib

# ---- Logging methods --------------------------------------------------------

"""
Print messages
"""
def info(message, type = "INFO"):
	print "[%s] %s" % (str(type), str(message))

def warning(message):
	info(message, type = "WARNING")

def error(message):
	info(message, type = "ERROR")

# ---- Utility methods --------------------------------------------------------

def which(executable):
	try:
		path = shell(".", ["which", executable], captureStdout=True)
	except:
		return None
	return path[0]

"""
Execute a shell command in a specific directory.
If it fails, it will throw.
"""
def shell(cwd, command, captureStdout=False, ignoreError=False):
	proc = subprocess.Popen(command, cwd=cwd, shell=False, stdout=(subprocess.PIPE if captureStdout else None),
			stderr=(subprocess.PIPE if captureStdout else None))

	output = []
	if proc.stdout:
		for line in iter(proc.stdout.readline, b''):
			line = line.rstrip()
			if captureStdout:
				output.append(line)
			else:
				print line

	out, error = proc.communicate()
	if proc.returncode != 0:
		message = "Fail to execute '%s' in '%s' (errno=%i)" % (" ".join(command), str(cwd), proc.returncode)
		if ignoreError:
			log.warning(message)
		else:
			raise Exception(message)

	return output

# ---- Module base class ------------------------------------------------------

"""
Defines modules supported. Each modules defines a certain set of optional
functions.
"""
class Module:

	def __init__(self, config):
		self.config = config

	"""
	Defines whether or not a module is present.
	Returns True if the module is present, False otherwise.
	"""
	@staticmethod
	def check(config):
		return True

	"""
	Return the default configuration of the module.
	"""
	@staticmethod
	def config():
		return {}

	"""
	Runs the initialization of the module.
	"""
	def init(self):
		pass

	def clean(self):
		pass

	def build(self, *args):
		pass


