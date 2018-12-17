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
import codecs

class RotatingLog:
	def __init__(self, directoryPath, prefix=None, maxLogs=10, maxLogSizeBytes=100 * 1024):
		self.maxLogSize = maxLogSizeBytes
		self.curLogSize = maxLogSizeBytes
		self.maxLogs = maxLogs
		self.curLogIndex = -1
		self.curLog = None
		self.prefix = prefix
		self.path = directoryPath

	def getLogPath(self, index):
		fileName = "%s%.8i.log" % (("%s." % self.prefix) if self.prefix else "", index)
		return os.path.join(self.path, fileName)

	def add(self, message):

		# Create a new log file
		if self.curLogSize >= self.maxLogSize:
			# Check if old log needs to be removed
			oldLog = self.getLogPath(self.curLogIndex - self.maxLogs)
			if os.path.exists(oldLog):
				os.remove(oldLog)
			self.curLogIndex += 1
			self.curLog = codecs.open(self.getLogPath(self.curLogIndex), "w", "utf-8")
			self.curLogSize = 0

		self.curLog.write(message)
		self.curLog.flush()
		self.curLogSize += len(message)

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
					"memory": int(fields[3]),
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
		return [{"pid": pid, "uptime": process["time"], "cpu": process["cpu"], "memory": process["memory"]} for pid, process in Daemon.getRunningProcesses(argList).items()]

	def start(self, appId, argList, context):

		def spawnServer(commandList, logDir, cwd):
			if os.fork():
				return

			def stdLogger(stderr, logStderr):
				for line in iter(stderr.readline, b''):
					logStderr.add(line.decode('utf-8', 'ignore'))

			# Ignore signal SIGHUP to act like nohup/screen
			signal.signal(signal.SIGHUP, signal.SIG_IGN)

			restartCounter = 0
			restart = True

			while restart:

				# Create the rotating loggers
				logStdout = RotatingLog(logDir, "stdout.%i" % (restartCounter))
				logStderr = RotatingLog(logDir, "stderr.%i" % (restartCounter))

				# Spawn the process
				process = subprocess.Popen(commandList, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, cwd=cwd, universal_newlines=True)

				# Log Stderr
				thread = threading.Thread(target=stdLogger, args=(process.stderr, logStderr))
				thread.start()

				# Log Stdout
				stdLogger(process.stdout, logStdout)

				# Restart if the process failed
				restart = (process.wait() != 0)
				restartCounter += 1

			os._exit(os.EX_OK)

		# Stop previous instances if any
		self.stop(appId, argList)

		# Create log directory entry and remove its content
		logDirPath = os.path.join(self.config["log"], appId)
		if os.path.exists(logDirPath):
			shutil.rmtree(logDirPath)
		os.makedirs(logDirPath)

		spawnServer(argList, logDir=logDirPath, cwd=context["cwd"])
