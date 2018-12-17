#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import json
import sys
import os
import imp
import subprocess
import shutil
import argparse
import datetime
import timeit
import math
import Queue
import threading
import time
import multiprocessing

GIT_REPOSITORY = "https://github.com/blaizard/irapp.git"
EXECUTABLE_PATH = os.path.realpath(__file__)
EXECUTABLE_DIRECTORY_PATH = os.path.realpath(os.path.dirname(__file__))
EXECUTABLE_NAME = os.path.basename(__file__)
DEPENDENCIES_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp")
TEMP_DIRECTORY_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp/temp")
ASSETS_DIRECTORY_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp/assets")
LOG_DIRECTORY_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp/log")
DEFAULT_CONFIG_FILE = ".irapp.json"

"""
Load the necessary dependencies
"""
def loadDependencies():
	try:
		if not os.path.isdir(DEPENDENCIES_PATH):
			raise Exception("Missing tool dependencies at %s" % (DEPENDENCIES_PATH))
		irapp = imp.load_module("irapp", None, DEPENDENCIES_PATH, ('', '', imp.PKG_DIRECTORY))
		if not irapp:
			raise Exception("Could not load dependencies")
	except Exception as e:
		lib.error("%s, abort." % (e))
		lib.info("Consider updating with '%s update'" % (EXECUTABLE_NAME))
		sys.exit(1)

	# Load the dependencies
	return irapp.loadModules(), irapp.getTypeList(), irapp.lib

"""
Read the configruation file and create it if it does not exists.
"""
def readConfig(args):
	global lib

	# Read the dependencies
	modules, types, lib = loadDependencies()

	config = {
		"lib": lib,
		"types": types,
		"root": EXECUTABLE_DIRECTORY_PATH,
		"assets": ASSETS_DIRECTORY_PATH,
		"log": LOG_DIRECTORY_PATH,
		"parallelism": multiprocessing.cpu_count(),
		"pimpl": {},
		"deploy": None
	}

	# Read the configuration
	try:
		f = open(args.configPath, "r")
		with f:
			try:
				configUser = json.load(f)
				config.update(configUser)
			except Exception as e:
				lib.error("Could not parse configuration file '%s'; %s" % (str(args.configPath), str(e)))
				sys.exit(1)
	except IOError:
		lib.warning("Could not open configuration file '%s', using default" % (str(args.configPath)))

	# Add the required module if to the type list
	requiredModuleList = args.modules.split(",") if args.modules else []
	for moduleId in requiredModuleList:
		if moduleId not in config["types"]:
			config["types"].append(moduleId)

	# Map and remove unsupported modules
	typeList = []
	for moduleId in config["types"]:
		isRequired = (moduleId in requiredModuleList)
		if moduleId not in modules:
			if isRequired:
				lib.error("Unknown required module '%s', abort" % (moduleId))
				sys.exit(1)
			lib.warning("Unknown module '%s', ignoring" % (moduleId))
			continue
		moduleClass = modules[moduleId]
		# Add module only if it checks correctly
		if moduleClass.check(config):
			typeList.append(moduleId)
			config["pimpl"][moduleId] = moduleClass
			# Update the default configuration
			defaultConfig = moduleClass.config()
			defaultConfig.update(config)
			config = defaultConfig
		elif isRequired:
			lib.error("Required module '%s' is not supported by this project, abort" % (moduleId))
			sys.exit(1)
	config["types"] = typeList

	# Initialize all the classes
	for moduleId, moduleClass in config["pimpl"].items():
		config["pimpl"][moduleId] = moduleClass(config)

	lib.info("Modules identified: %s" % (", ".join(config["types"])))
	return config

# ---- Supported actions -----------------------------------------------------

"""
Entry point for all action mapped to the supported and enabled modules.
"""
def action(args):
	# Read the configuration
	config = readConfig(args)

	# If this is a init command, clean up the assets directory
	if os.path.isdir(ASSETS_DIRECTORY_PATH):
		shutil.rmtree(ASSETS_DIRECTORY_PATH)

	lib.info("Running command '%s' in '%s'" % (str(args.command), str(config["root"])))
	for moduleId in config["types"]:
		if args.command == "init":
			config["pimpl"][moduleId].init()
		elif args.command == "build":
			config["pimpl"][moduleId].build(args.type)
		elif args.command == "clean":
			config["pimpl"][moduleId].clean()

def deploy(args):
	# Read the configuration
	config = readConfig(args)

	deployDescs = config["deploy"]
	if isinstance(deployDescs, str):
		deployDescs = [config["deploy"]]
	if isinstance(deployDescs, list):
		deployDescs = {"default": deployDescs}

	# Select a specific ID if needed
	if args.id:
		if args.id in deployDescs:
			deployDescs = {args.id: deployDescs[args.id]}
		else:
			lib.error("Unknown application ID '%s'" % (args.id))
			sys.exit(1)

	if args.command == "start":
		lib.start(deployDescs, config)
	elif args.command == "stop":
		lib.stop(deployDescs, config)
	lib.status(deployDescs, config)

"""
Print information regarding the program and loaded modules
"""
def info(args):
	# Read the configuration
	config = readConfig(args)

	lib.info("Hash: %s" % (str(getCurrentHash())))
	for moduleId in config["types"]:
		config["pimpl"][moduleId].info()

def runWorker(command, hideOutput, queue, signal):
	lib.shell(command, captureStdout=hideOutput, queue=queue, signal=signal)

"""
Run the program specified
"""
def run(args):

	# Custom process class to control process pool
	class Thread(threading.Thread):
		def __init__(self, *args, **kwargs):
			threading.Thread.__init__(self, *args, **kwargs)
			self._threadException = None

		def run(self):
			try:
				threading.Thread.run(self)
			except Exception as e:
				self._threadException = e

		def clearException(self):
			self._threadException = None

		@property
		def exception(self):
			return self._threadException

	# Read the configuration
	config = readConfig(args)

	# Build the list of commands to be executed
	commandList = [cmd.split() for cmd in args.commandList] + ([args.args] if args.args else [])

	# Number of iterations to be performed (0 for endless)
	totalIterations = args.iterations if args.iterations else (0 if args.endless else (0 if args.duration else 1))

	# Calculate the timeout
	isAutoTimeout = True if args.timeout < 0 else False
	timeout = 0 if args.timeout < 0 else args.timeout

	# Define the number of jobs
	nbJobs = args.nbJobs if args.nbJobs > 0 else config["parallelism"]

	optionsStrList = []
	if nbJobs > 1:
		optionsStrList.append("%i jobs" % (nbJobs))
	if totalIterations > 1:
		optionsStrList.append("%i iterations" % (totalIterations))
	elif totalIterations == 0:
		optionsStrList.append("endless mode")
	if args.duration:
		optionsStrList.append("%is" % (args.duration))
	if isAutoTimeout:
		optionsStrList.append("timeout auto")
	elif timeout > 0:
		optionsStrList.append("%is timeout" % (timeout))
	optionsStr = " [%s]" % (", ".join(optionsStrList)) if len(optionsStrList) else ""

	if len(commandList) == 1:
		lib.info("Running command '%s'%s" % (" ".join(commandList[0]), optionsStr))
	elif len(commandList) > 1:
		lib.info("Running commands %s%s" % (", ".join([("'" + " ".join(cmd) + "'") for cmd in commandList]), optionsStr))
	else:
		lib.error("No command was executed")
		sys.exit(1)

	# Pre run the supported modules
	for moduleId in config["types"]:
		config["pimpl"][moduleId].runPre(commandList)

	# Create the pool of workers
	workerList = [None for i in range(nbJobs)]
	workerContext = [None] * nbJobs
	workerErrors = {}

	hideOutput = (totalIterations != 1) and not args.verbose
	startingTime = datetime.datetime.now()
	startingTimeIteration = datetime.datetime.now()
	totalTimeS = 0
	nbIterations = 0
	nbWorkers = 0
	commandIndex = 0
	curIteration = 0
	iterations = {}

	try:

		while not bool(workerErrors):

			# Fill the worker pool and update the number of workers currently working
			nbWorkers = 0
			for i in range(nbJobs):

				# If a worker is registered
				if workerList[i]:
					workerElpasedTimeS = timeit.default_timer() - workerList[i]["time"]

					# Check if it has timed out
					if timeout and workerElpasedTimeS > timeout:
						workerErrors[i] = ["Timeout (%is) on '%s'" % (timeout, workerList[i]["command"])]
						raise Exception("<<<< Timeout (%is) >>>>" % (timeout))

					elif not workerList[i]["worker"].is_alive():
						# The worker is completed
						if workerList[i]["worker"].exception:
							workerErrors[i] = [str(workerList[i]["worker"].exception)]
							raise Exception("<<<< FAILURE >>>>")

						workerList[i]["worker"].join()
						workerIteration = workerList[i]["iterationId"]
						workerList[i] = None
					
						# Increase the iteration number and check if one full iteration is completed
						iterations[workerIteration] = ({"nb": iterations[workerIteration]["nb"] + 1, "time": iterations[workerIteration]["time"] + workerElpasedTimeS}) if workerIteration in iterations else {"nb": 1, "time": workerElpasedTimeS}
						if iterations[workerIteration]["nb"] == len(commandList):
							nbIterations += 1
							totalTimeS += iterations[workerIteration]["time"]
							startingTimeIteration = datetime.datetime.now()
							iterations.pop(workerIteration)
					else:
						nbWorkers += 1

				# If not registered, add it
				if not workerList[i] and (totalIterations == 0 or curIteration < totalIterations):
					workerContext[i] = Queue.Queue()
					signal = threading.Event()
					workerList[i] = {
						"command": " ".join(commandList[commandIndex]),
						"worker": Thread(target=runWorker, args=(commandList[commandIndex], hideOutput, workerContext[i] if hideOutput else None, signal)),
						"time": timeit.default_timer(),
						"iterationId": curIteration,
						"signal": signal
					}
					workerList[i]["worker"].start()
					# Increase the command index and the interation
					commandIndex += 1
					if commandIndex == len(commandList):
						commandIndex = 0
						curIteration += 1
					nbWorkers += 1

			if hideOutput:
				sys.stdout.write("\rTime: %s, %i iteration(s), average %s, timeout %s, %i job(s)" % (
						str(datetime.datetime.now() - startingTime),
						nbIterations,
						str(float("%.6f" % (totalTimeS / nbIterations))) + "s" if nbIterations else "?",
						("%is" % (timeout)) if timeout else "-",
						nbWorkers))
				sys.stdout.flush()

			# Update the timeout, if auto timeout is selected
			if isAutoTimeout and nbIterations:
				timeout = math.ceil(totalTimeS / nbIterations * 5)

			# If time reached its limit, break
			if args.duration and (datetime.datetime.now() - startingTime).total_seconds() > args.duration:
				break

			# If the number of iterations reached its limit, break
			if totalIterations and (nbIterations >= totalIterations):
				break

	except (KeyboardInterrupt, SystemExit) as e:
		print("")
		lib.error("<<<< Keyboard Interrupt >>>>")

	except BaseException as e:
		print("")
		lib.error(str(e))

	else:
		print("")

	# Ensure the workers are terminated
	# Set the signal to the thread and wait until it is completed
	sys.stdout.write("Kill pending jobs... (can take up to 10s)\r")
	sys.stdout.flush()
	for i in range(nbJobs):
		if workerList[i]:
			workerList[i]["signal"].set()
	for i in range(nbJobs):
		if workerList[i] and workerList[i]["worker"].is_alive():
			workerList[i]["worker"].clearException()
			errorMsg = None
			try:
				workerList[i]["worker"].join(10)
				errorMsg = workerList[i]["worker"].exception
			except:
				errorMsg = "Cannot terminate process"
			if errorMsg:
				workerErrors[i] = workerErrors[i] if i in workerErrors else []
				workerErrors[i].append(str(errorMsg))

	if bool(workerErrors):
		for i, errorList in workerErrors.items():
			if workerList[i]:
				# Print the content of the log
				lib.error("---- (worker #%i) -------------------------------------------------------------" % (i))
				for line in list(workerContext[i].queue):
					print(line)
				lib.error("Failure cause: %s" % (", ".join(errorList)))
		sys.exit(1)

	# Post run the supported modules
	for moduleId in config["types"]:
		config["pimpl"][moduleId].runPost(commandList)

"""
Return the current hash or None if not available
"""
def getCurrentHash():
	hashPath = os.path.join(DEPENDENCIES_PATH, ".hash")
	if os.path.isfile(hashPath):
		with open(hashPath, "r") as f:
			return f.read()
	return None

"""
Updating the tool
"""
def update(args):

	# Read the current hash
	currentGitHash = getCurrentHash()
	lib.info("Current version: %s" % (str(currentGitHash)))

	if not args.force:
		gitRemote = lib.shell(["git", "ls-remote", GIT_REPOSITORY, "HEAD"], captureStdout=True)
		gitHash = gitRemote[0].lstrip().split()[0]
		lib.info("Latest version available: %s" % (gitHash))

		# Need to update
		if currentGitHash == gitHash:
			lib.info("Already up to date!")
			return
	lib.info("Updating to latest version...")

	# Create and cleanup the temporary directory
	if os.path.isdir(TEMP_DIRECTORY_PATH):
		shutil.rmtree(TEMP_DIRECTORY_PATH)
	if not os.path.exists(TEMP_DIRECTORY_PATH):
		os.makedirs(TEMP_DIRECTORY_PATH)

	# Clone the latest repository into this path
	lib.shell(["git", "clone", GIT_REPOSITORY, "."], cwd=TEMP_DIRECTORY_PATH)

	# Read the version changes
	changeList = None
	if currentGitHash:
		changeList = lib.shell(["git", "log", "--pretty=\"%s\"", "%s..HEAD" % (currentGitHash)], cwd=TEMP_DIRECTORY_PATH, captureStdout=True, ignoreError=True) 

	# These are the location of the files for the updated and should NOT change over time
	executableName = "app.py"
	dependenciesDirectoryName = ".irapp"

	# Remove everything inside the dependencies path, except the current temp directory and the log directory
	tempFullPath = os.path.realpath(TEMP_DIRECTORY_PATH)
	logFullPath = os.path.realpath(LOG_DIRECTORY_PATH)
	for root, dirs, files in os.walk(DEPENDENCIES_PATH):
		for name in files:
			os.remove(os.path.join(root, name))

		for name in dirs:
			fullPath = os.path.realpath(os.path.join(root, name))
			if not tempFullPath.startswith(fullPath) and not logFullPath.startswith(fullPath):
				shutil.rmtree(fullPath)
			# Do not look into this path
			if tempFullPath == fullPath or logFullPath == fullPath:
				dirs.remove(name)

	# Move the content of the dependencies directory into the new one
	dependenciesDirectoryPath = os.path.join(TEMP_DIRECTORY_PATH, dependenciesDirectoryName)
	dependenciesContentFiles = os.listdir(dependenciesDirectoryPath)
	for fileName in dependenciesContentFiles:
		shutil.move(os.path.join(dependenciesDirectoryPath, fileName), DEPENDENCIES_PATH)

	# Replace main source file
	shutil.move(os.path.join(TEMP_DIRECTORY_PATH, executableName), EXECUTABLE_PATH)

	# Read again current hash
	gitRawHash = lib.shell(["git", "rev-parse", "HEAD"], cwd=TEMP_DIRECTORY_PATH, captureStdout=True)
	gitHash = gitRawHash[0].lstrip().split()[0]

	# Remove temporary directory
	try:
		shutil.rmtree(TEMP_DIRECTORY_PATH)
	except Exception as e:
		lib.warning("Could not delete %s, %s" % (TEMP_DIRECTORY_PATH, e))

	# Create hash file
	with open(os.path.join(DEPENDENCIES_PATH, ".hash"), "w") as f:
		f.write(gitHash)

	lib.info("Update to %s succeed." % (gitHash))
	if changeList:
		lib.info("Change(s):")
		for change in changeList:
			lib.info("- %s" % (change))

# ---- Lib implementation -----------------------------------------------------

"""
Minimalistic lib implementation as a fallback
"""
class lib:
	@staticmethod
	def info(message, type = "INFO"):
		print("[%s] %s" % (str(type), str(message)))

	@staticmethod
	def warning(message):
		lib.info(message, type = "WARNING")

	@staticmethod
	def error(message):
		lib.info(message, type = "ERROR")

	"""
	Execute a shell command in a specific directory.
	If it fails, it will throw.
	"""
	@staticmethod
	def shell(command, cwd=".", captureStdout=False, ignoreError=False, queue=None, signal=None):

		def enqueueOutput(out, queue, signal):
			for line in iter(out.readline, b''):
				queue.put(line.rstrip().decode('utf-8'))
			out.close()
			signal.set()

		isReturnStdout = True if captureStdout and not queue else False

		proc = subprocess.Popen(command, cwd=cwd, shell=False, stdout=(subprocess.PIPE if captureStdout or queue else None),
			stderr=(subprocess.STDOUT if captureStdout or queue else None))

		if not queue:
			queue = Queue.Queue()

		if not signal:
			signal = threading.Event()

		# Wait until a signal is raised or until the the process is terminated
		if captureStdout:
			outputThread = threading.Thread(target=enqueueOutput, args=(proc.stdout, queue, signal))
			outputThread.start()
			signal.wait()
		else:
			while proc.poll() is None:
				time.sleep(0.1)
				if signal.is_set():
					break

		errorMsgList = []

		# Kill the process (max 5s)
		if proc.poll() is None:
			def processTerminateTimeout():
				proc.kill()
				errorMsgList.append("stalled")
			timer = threading.Timer(5, processTerminateTimeout)
			try:
				timer.start()
				proc.terminate()
				proc.wait()
			finally:
				timer.cancel()

		if proc.returncode != 0:
			errorMsgList.append("return.code=%s" % (str(proc.returncode)))

		if len(errorMsgList):
			message = "Failed to execute '%s' in '%s': %s" % (" ".join(command), str(cwd), ", ".join(errorMsgList))
			if ignoreError:
				lib.warning(message)
			else:
				raise Exception(message)

		# Build the output list
		return list(queue.queue) if isReturnStdout else []

# -----------------------------------------------------------------------------

"""
Entry point fo the script
"""
if __name__ == "__main__":

	commandActions = {
		"info": info,
		"init": action,
		"clean": action,
		"build": action,
		"start": deploy,
		"stop": deploy,
		"status": deploy,
		"run": run,
		"update": update
	}

	parser = argparse.ArgumentParser(description = "Application helper script.")
	parser.add_argument("-c", "--config", action="store", dest="configPath", default=DEFAULT_CONFIG_FILE, help="Path of the build definition (default=%s)." % (DEFAULT_CONFIG_FILE))
	parser.add_argument("-v", "--version", action='version', version="%s hash: %s" % (os.path.basename(__file__), str(getCurrentHash())))
	parser.add_argument("-m", "--modules", action='store', dest="modules", default="", help="Enforce the use of specific modules (comma separated). If one of the given module fails to setup, the program returns with an error.")

	subparsers = parser.add_subparsers(dest="command", help='List of available commands.')

	parserRun = subparsers.add_parser("run", help='Execute the specified commmand.')
	parserRun.add_argument("-e", "--endless", action="store_true", dest="endless", default=False, help="Run the command endlessly (until it fails).")
	parserRun.add_argument("-v", "--verbose", action="store_true", dest="verbose", default=False, help="Force printing the output while running the command.")
	parserRun.add_argument("-j", "--jobs", type=int, action="store", dest="nbJobs", default=1, help="Number of jobs to run in parallel. If 0 is used, the system will automatically pick the number of jobs based on the number of core.")
	parserRun.add_argument("-c", "--cmd", action="append", dest="commandList", default=[], help="Command to be executed. More than one command can be executed simultaneously sequentially. If combined with --jobs the commands will be executed simultaneously.")
	parserRun.add_argument("-i", "--iterations", type=int, action="store", dest="iterations", default=0, help="Number of iterations to be performed.")
	parserRun.add_argument("-d", "--duration", type=int, action="store", dest="duration", default=0, help="Run the commands for a specific amount of time (in seconds).")
	parserRun.add_argument("-t", "--timeout", type=int, action="store", dest="timeout", default=-1, help="Timeout (in seconds) until the iteration should be considered as invalid. If set to -1, an automatic timeout is set, calculated based on the previous run. If set to 0, no timeout is set.")
	parserRun.add_argument("args", nargs=argparse.REMAINDER, help='Extra arguments to be passed to the command executed.')

	subparsers.add_parser("info", help='Display information about the script and the loaded modules.')
	subparsers.add_parser("init", help='Initialize or setup the project environment.')
	subparsers.add_parser("clean", help='Clean the project environment from build artifacts.')
	parserBuild = subparsers.add_parser("build", help='Build the project.')
	parserBuild.add_argument("type", action='store', nargs='?', default=None, help='Build type.')

	parserUpdate = subparsers.add_parser("update", help='Update the tool to the latest version available.')
	parserUpdate.add_argument("-f", "--force", action="store_true", dest="force", default=False, help="If set, it will update even if the last version is detected.")

	parserStart = subparsers.add_parser("start", help="Deploy the application.")
	parserStart.add_argument('id',  action='store', nargs='?', default=None, help='The application ID to be started.')
	parserStop = subparsers.add_parser("stop", help="Stop the application previously deployed.")
	parserStop.add_argument('id',  action='store', nargs='?', default=None, help='The application ID to be stopped.')
	parserStatus = subparsers.add_parser("status", help="Display the status of the applications.")
	parserStatus.add_argument('id',  action='store', nargs='?', default=None, help='The application ID to be prompted.')

	args = parser.parse_args()

	# Excecute the action
	fct = commandActions.get(args.command, None)
	if fct == None:
		lib.error("Invalid command '%s'" % (str(args.command)))
		parser.print_help()
		sys.exit(1)

	# Execute the proper action
	fct(args)
