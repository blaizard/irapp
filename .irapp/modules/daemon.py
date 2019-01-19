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
import timeit

# Import local lib. The different path is needed as relative import beyond the top level
# are not supported. Note if we use the workaround for all cases, then the module lib would be loaded twice
# and therefore configurations such as 'logPrefix' would be lost.
if __name__ == "__main__":
	sys.path.append(os.path.dirname(os.path.dirname(__file__)))
	import lib
else:
	from .. import lib

class Daemon(lib.Module):

	@staticmethod
	def check(config):
		return True

	"""
	Return the current process list and their PID
	"""
	@staticmethod
	def getProcesses(includeCpuMem=False):
		processes = {}
		if sys.platform == "win32":
			# List the processes
			output = lib.shell(["wmic", "process", "get", "processid,parentprocessid,workingsetsize,commandline", "/format:csv"], capture=True)
			for line in output[2:]:
				split = line.split(",")
				if len(split) > 4:
					command = (",".join(split[1:-3])).strip()
					ppid = split[-3]
					pid = split[-2]
					memory = split[-1]
					if command:
						try:
							processes[int(pid)] = {
								"ppid": int(ppid),
								"command": command,
								"cpu": 0,
								"memory": int(memory)
							}
						except:
							pass
			# Add cpu and memory
			if includeCpuMem:
				output = lib.shell(["wmic", "path", "win32_perfformatteddata_perfproc_process", "get", "percentprocessortime,idprocess", "/format:csv"], capture=True)
				for line in output[2:]:
					split = line.split(",")
					if len(split) > 2:
						pid = split[1]
						cpu = split[2]
						if int(pid) in processes:
							processes[int(pid)]["cpu"] = float(cpu)
		else:
			output = lib.shell(["ps", "-eo", "pid,ppid,rss,%cpu,command"], capture=True)
			for line in output[1:]:
				fields = line.strip().split()
				processes[int(fields[0])] = {
					"ppid": int(fields[1]),
					"memory": float(fields[2]) * 1024,
					"cpu": float(fields[3]),
					"command": " ".join(fields[4:])
				}
		return processes

	@staticmethod
	def getRunningProcesses(appId=None, childrenPids=set(), includeCpuMem=False):
		# Get process signature
		cmdRegexpr = re.compile("%s\\.pyc?\\s+(%s)" % (re.escape(os.path.splitext(__file__)[0]), re.escape(appId))) if appId else re.compile("%s\\.pyc?\\s+([^\\s]+)" % (re.escape(os.path.splitext(__file__)[0])))
		# Check if the same process is running
		runningParentPis = {}
		processes = Daemon.getProcesses(includeCpuMem=includeCpuMem)

		# Search for the parent process (that are identifiable by the regexpr)
		for pid, process in processes.items():
			match = re.search(cmdRegexpr, process["command"])
			if match:
				# Format: { pid: {id: <appId>, ...} }
				runningParentPis[pid] = dict(process, id=match.group(1))

		# Return all pid associated with this parent
		def getProcessChildren(ppid):
			childPids = set()
			for pid, process in processes.items():
				if process["ppid"] == ppid:
					if pid not in childPids:
						childPids.add(pid)
						childPids |= getProcessChildren(pid)
			return childPids

		# Look for all the childs of these parent processes
		runningProcesses = {}
		for ppid, pprocess in runningParentPis.items():
			matches = {pid: dict(process, id=pprocess["id"]) for pid, process in processes.items() if process["ppid"] == ppid}
			if not matches:
				matches = {ppid: dict(pprocess, ppid=None)}
			runningProcesses.update(matches)

		# Update the memory
		for ppid in runningProcesses.keys():
			pids = getProcessChildren(ppid)
			childrenPids |= pids
			if includeCpuMem:
				for pid in pids:
					runningProcesses[ppid]["memory"] += processes[pid]["memory"]
					runningProcesses[ppid]["cpu"] += processes[pid]["cpu"]

		return runningProcesses

	@staticmethod
	def killProcess(pid):
		if sys.platform == "win32":
			subprocess.call(["taskkill", "/f", "/pid", "%i" % (pid)], stdout=open(os.devnull, 'w'), stderr=open(os.devnull, 'w'), shell=True)
		else:
			os.kill(pid, signal.SIGKILL)
		os.waitpid(pid)

	def stop(self, appId=None):
		# Get the list of running process
		childrenPids = set()
		runningProcesses = Daemon.getRunningProcesses(appId, childrenPids=childrenPids)

		# Delete the running processes if any
		for pid, process in runningProcesses.items():
			lib.info("Stopping daemon '%s' with pid %i" % (process["id"], process["ppid"]))
			# Stop the parent process for to make sure ti will not restart the child process
			if process["ppid"]:
				try:
					Daemon.killProcess(process["ppid"])
				except:
					pass # Ignore errors as the process might be gone by then
		# Deleting all children PIDs if still alive
		if childrenPids:
			lib.info("Stopping children with pid(s): %s" % (", ".join([str(pid) for pid in childrenPids])))
			for pid in childrenPids:
				# Stop the process itself
				try:
					Daemon.killProcess(pid)
				except:
					pass # Ignore errors as the process might be gone by then

	def status(self, appId=None):
		# Ceil the CPU at 100.A higher value might happen in case of multiprocessors, but it is fair to say that if one processor
		# is already saturated, it already reaches its full potential
		return [{"id": process["id"], "pid": pid, "cpu": min(process["cpu"], 100), "memory": process["memory"]} for pid, process in Daemon.getRunningProcesses(appId, includeCpuMem=True).items()]

	def start(self, appId, commandList, context):

		# Stop previous instances if any
		self.stop(appId)

		# Workaround on Windows machine, the environment path is not searched to find the executable, hence
		# we need to do this manually.
		if sys.platform =='win32':
			fullPath = lib.which(commandList[0], cwd=context["cwd"])
			if fullPath:
				commandList[0] = fullPath

		# Start a subprocess with the executabel information
		process = subprocess.Popen([sys.executable, __file__, appId, self.config["log"]] + commandList, stdin=None, stdout=None, stderr=None, shell=False, cwd=context["cwd"])

		# 2s timeout before checking the status (one is too low)
		# This is to gfive enough time for the process to start
		time.sleep(2)
		if process.poll() != None and process.returncode != 0:
			raise Exception("Unable to start daemon '%s' in '%s'" % (" ".join(commandList), context["cwd"]))

		lib.info("Started daemon '%s'" % (appId))

"""
Entry point fo the script
"""
if __name__ == "__main__":

	def stdLogger(process, stream, log):
		while True:
			line = stream.readline()
			if line:
				log.add(line)
			elif process.poll() is not None:
				break

	if sys.platform != "win32":
		# Ignore signal SIGHUP to act like nohup/screen (on unix machine)
		signal.signal(signal.SIGHUP, signal.SIG_IGN)

	appId = sys.argv[1]
	logDir =  sys.argv[2]
	commandList = sys.argv[3:]

	restartCounter = 0
	restartFailureCounter = 0
	restart = True

	# Failure that opens with the next X seconds of the process being open
	# If they happen too often the process will be stopped
	rapidConsequentFailureCounter = 0

	factory = lib.LogFactory(logDir, appId, Daemon.getRunningProcesses(appId).keys())

	# The out and err streams
	logStdout = logStderr = None

	try:
		while restart:

			# Spawn the process
			try:
				process = subprocess.Popen(commandList, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False, universal_newlines=True)
				restartFailureCounter = 0
			except BaseException as e:
				restartFailureCounter += 1
				if restartCounter == 0 or restartFailureCounter >= 5:
					raise e
				logStderr.add("Could not start '%s': %s, restarting in 5s" % (" ".join(commandList), str(e)))
				time.sleep(5)
				continue

			timeStart = timeit.default_timer()

			# Create the rotating loggers
			logStdout, logStderr = factory.createLogs(process.pid)

			# Log Stderr
			thread = threading.Thread(target=stdLogger, args=(process, process.stderr, logStderr))
			thread.start()

			# Log Stdout
			stdLogger(process, process.stdout, logStdout)

			# Restart if the process failed
			restart = (process.wait() != 0)
			# If it fails within the first 60s
			if restart and (timeit.default_timer() - timeStart) < 60:
				rapidConsequentFailureCounter += 1
				if rapidConsequentFailureCounter > 3:
					raise Exception("Too many (>%i) consequent rapid (<%is) failures detected, aborting." % (3, 60))
			else:
				rapidConsequentFailureCounter = 0

			restartCounter += 1
	except BaseException as e:
		if logStderr:
			logStderr.add(str(e))
		raise e

	sys.exit(0)
