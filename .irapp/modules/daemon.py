#!/usr/bin/python
# -*- coding: iso-8859-1 -*-
import sys
import os
import time
import signal
import platform
import subprocess
import re
import threading
import time
import errno

irappDirectoryPath = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, irappDirectoryPath)

# Import local lib
import lib

class Daemon(lib.Module):

	@staticmethod
	def check(config):
		return (platform.system() != "Windows")

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
			output = lib.shell(["ps", "-eo", "pid,ppid,rss,%cpu,command"], captureStdout=True)
			for line in output[1:]:
				fields = line.strip().split()
				processes[int(fields[0])] = {
					"ppid": int(fields[1]),
					"memory": float(fields[2]),
					"cpu": float(fields[3]),
					"command": " ".join(fields[4:])
				}
		return processes

	@staticmethod
	def getRunningProcesses(appId = None):
		# Get process signature
		cmdRegexpr = re.compile("%s\\.pyc?\\s+(%s)" % (re.escape(os.path.splitext(__file__)[0]), re.escape(appId))) if appId else re.compile("%s\\.pyc?\\s+([^\\s]+)" % (re.escape(os.path.splitext(__file__)[0])))
		# Check if the same process is running
		runningParentPis = {}
		processes = Daemon.getProcesses()
		# Search for the parent process (that are identifiable by the regexpr)
		for pid, process in processes.items():
			match = re.search(cmdRegexpr, process["command"])
			if match:
				runningParentPis[pid] = match.group(1)
		# Look for the child of these parent processes
		runningProcesses = {}
		for pid, process in processes.items():
			if process["ppid"] in runningParentPis:
				runningProcesses[pid] = dict(process, id=runningParentPis[process["ppid"]])
		return runningProcesses

	@staticmethod
	def isProcessRunning(pid):
		try:
			os.kill(pid, 0)
		except OSError as err:
			if err.errno == errno.ESRCH:
				return False
		return True

	def stop(self, appId=None):
		# Get the list of running process
		runningProcesses = Daemon.getRunningProcesses(appId)

		# Delete the running processes if any
		for pid, process in runningProcesses.items():
			lib.info("Stopping daemon '%s' with pid %i" % (process["id"], pid))
			# Stop the parent process
			try:
				os.kill(process["ppid"], signal.SIGKILL)
				while Daemon.isProcessRunning(process["ppid"]):
					time.sleep(0.1)
			except:
				pass # Ignore errors as the process might be gone by then
			# Stop the process itself
			try:
				os.kill(pid, signal.SIGKILL)
				while Daemon.isProcessRunning(pid):
					time.sleep(0.1)
			except:
				pass # Ignore errors as the process might be gone by then

	def status(self, appId=None):
		return [{"id": process["id"], "pid": pid, "cpu": process["cpu"], "memory": process["memory"] * 1024} for pid, process in Daemon.getRunningProcesses(appId).items()]

	def start(self, appId, commandList, context):

		# Stop previous instances if any
		self.stop(appId)

		# Start a subprocess with the executabel information
		process = subprocess.Popen([sys.executable, __file__, appId, self.config["log"]] + commandList, stdin=None, stdout=None, stderr=None, shell=False, cwd=context["cwd"])

		# 1s timeout before checking the status
		time.sleep(1)
		if process.poll() != None:
			raise Exception("Unable to start daemon '%s' in '%s'" % (" ".join(commandList), context["cwd"]))

		lib.info("Started daemon '%s'" % (appId))

"""
Entry point fo the script
"""
if __name__ == "__main__":

	def stdLogger(stream, log):
		for line in iter(stream.readline, b''):
			log.add(line)

	# Ignore signal SIGHUP to act like nohup/screen
	signal.signal(signal.SIGHUP, signal.SIG_IGN)

	appId = sys.argv[1]
	logDir =  sys.argv[2]
	commandList =  sys.argv[3:]

	restartCounter = 0
	restartFailureCounter = 0
	restart = True

	factory = lib.LogFactory(logDir, appId, Daemon.getRunningProcesses(appId).keys())

	while restart:

		# Spawn the process
		try:
			process = subprocess.Popen(commandList, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, universal_newlines=True)
			restartFailureCounter = 0
		except BaseException as e:
			restartFailureCounter += 1
			if restartCounter == 0 or restartFailureCounter >= 5:
				sys.exit(1)
			logStderr.add("Could not start '%s': %s, restarting in 5s" % (" ".join(commandList), str(e)))
			time.sleep(5)
			continue

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

	sys.exit(0)
