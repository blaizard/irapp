#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import sys
import time
import signal
import platform
import subprocess
import re

class Deploy(lib.Module):

	@staticmethod
	def check(config):
		return True #("command" in config)

	@staticmethod
	def config():
		return {
			"command": ["sleep", "10"]
		}

	"""
	Return the current process list and their PID
	"""
	@staticmethod
	def getProcessList():
		processes = []
		if platform.system() == "Windows":
			output = lib.shell(["tasklist"], captureStdout=True)
			output = lib.shell(["wmic", "process", "get", "processid,commandline"], captureStdout=True)
			# to complete
		else:
			output = lib.shell(["ps", "-ef"], captureStdout=True)
			output.pop()
			for line in output:
				fields = line.strip().split()
				processes.append({
					"pid": fields[1],
					"command": " ".join(fields[7:])
				})
		return processes

	def deploy(self, *args):

		def spawnServer(text):
			if os.fork():
				return

			# Ignore signal SIGHUP to act like nohup/screen
			signal.signal(signal.SIGHUP, signal.SIG_IGN)

			# Spawn the process
			subprocess.call(self.config["command"], stdin=None, stdout=None, stderr=None, shell=False)

			os._exit(os.EX_OK)

		# Create the regexpr for the command
		cmdRegexpr = re.compile("\\s+".join([re.escape(arg) for arg in self.config["command"]]))
		# Check if the same process is running
		runningProcessList = []
		processList = Deploy.getProcessList()
		for process in processList:
			if re.search(cmdRegexpr, process["command"]):
				runningProcessList.append(process)

		print(runningProcessList)
		spawnServer("Hello")
