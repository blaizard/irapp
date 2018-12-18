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
import shutil
import threading
import time
import errno

class Daemon(lib.Module):

	@staticmethod
	def check(config):
		return True #("command" in config)

	"""
	Return the current process list and their PID
	"""
	@staticmethod
	def getProcesses():
		processes = {}
		if platform.system() == "Windows":
			#output = lib.shell(["tasklist"], captureStdout=True)
			output = lib.shell(["wmic", "process", "get", "processid,commandline"], captureStdout=True)
			# to complete
		else:
			output = lib.shell(["ps", "-eo", "pid,ppid,stime,rss,%cpu,command"], captureStdout=True)
			for line in output[1:]:
				fields = line.strip().split()
				processes[int(fields[0])] = {
					"ppid": int(fields[1]),
					"time": fields[2],
					"memory": float(fields[3]),
					"cpu": float(fields[4]),
					"command": " ".join(fields[5:])
				}
		return processes

	@staticmethod
	def getRunningProcesses(argList):
		# Get process signature
		cmdRegexpr = re.compile("\\s+".join([re.escape(arg) for arg in argList]))
		# Check if the same process is running
		runningProcesses = {}
		processes = Daemon.getProcesses()
		for pid, process in processes.items():
			if re.search(cmdRegexpr, process["command"]):
				runningProcesses[pid] = process
		return runningProcesses

	@staticmethod
	def isProcessRunning(pid):
		try:
			os.kill(pid, 0)
		except OSError as err:
			if err.errno == errno.ESRCH:
				return False
		return True

	def stop(self, appId, argList):
		# Get the list of running process
		runningProcesses = Daemon.getRunningProcesses(argList)

		# Delete the running processes if any
		for pid, process in runningProcesses.items():
			lib.info("Stopping daemon '%s' with pid %i" % (appId, pid))
			# Stop the parent process
			os.kill(process["ppid"], signal.SIGKILL)
			while Daemon.isProcessRunning(process["ppid"]):
				time.sleep(0.1)
			# Stop the process itself
			os.kill(pid, signal.SIGKILL)
			while Daemon.isProcessRunning(pid):
				time.sleep(0.1)

	def status(self, appId, argList):
		return [{"pid": pid, "uptime": process["time"], "cpu": process["cpu"], "memory": process["memory"] * 1024} for pid, process in Daemon.getRunningProcesses(argList).items()]

	def start(self, appId, commandList, context):

		def stdLogger(stream, log):
			for line in iter(stream.readline, b''):
				log.add(line.decode('utf-8', 'ignore'))

		# Stop previous instances if any
		self.stop(appId, commandList)

		if os.fork():
			return

		# Ignore signal SIGHUP to act like nohup/screen
		signal.signal(signal.SIGHUP, signal.SIG_IGN)

		restartCounter = 0
		restart = True

		factory = self.logFactory(appId, Daemon.getRunningProcesses(commandList).keys())

		while restart:

			# Spawn the process
			process = subprocess.Popen(commandList, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, cwd=context["cwd"], universal_newlines=True)

			# Create the rotating loggers
			logStdout, logStderr = factory.createLogs(process.pid)

			# Log Stderr
			thread = threading.Thread(target=stdLogger, args=(process.stderr, logStderr))
			thread.start()

			# Log Stdout
			stdLogger(process.stdout, logStdout)

			# Restart if the process failed
			restart = (process.wait() != 0)
			restartCounter += 1

		os._exit(os.EX_OK)
