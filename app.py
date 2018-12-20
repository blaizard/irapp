#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import json
import sys
import os
import imp
import subprocess
import shutil
import shlex
import argparse
import datetime
import timeit
import math
import threading
import time
import multiprocessing

try:
	from queue import Queue
except:
	from Queue import Queue

GIT_REPOSITORY = "https://github.com/blaizard/irapp.git"
EXECUTABLE_PATH = os.path.realpath(__file__)
EXECUTABLE_DIRECTORY_PATH = os.path.realpath(os.path.dirname(__file__))
EXECUTABLE_NAME = os.path.basename(__file__)
DEPENDENCIES_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp")
TEMP_DIRECTORY_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp/temp")
ASSETS_DIRECTORY_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp/assets")
LOG_DIRECTORY_PATH = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp/log")
DEFAULT_CONFIG_FILE = os.path.join(EXECUTABLE_DIRECTORY_PATH, ".irapp.json")

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
def readConfig(args, verbose=True):
	global lib

	# Read the dependencies
	modules, types, lib = loadDependencies()

	config = {
		"lib": lib,
		"types": [],
		"root": EXECUTABLE_DIRECTORY_PATH,
		"assets": ASSETS_DIRECTORY_PATH,
		"log": LOG_DIRECTORY_PATH,
		"parallelism": multiprocessing.cpu_count(),
		"pimpl": {},
		"start": {}
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
		if verbose:
			lib.warning("Could not open configuration file '%s', using default" % (str(args.configPath)))

	# Map and remove unsupported modules
	typeList = []
	for moduleId in types:
		moduleClass = modules[moduleId]
		# Add module only if it checks correctly
		if moduleId in config["types"] or moduleClass.check(config):
			typeList.append(moduleId)
			config["pimpl"][moduleId] = moduleClass
			# Update the default configuration
			defaultConfig = moduleClass.config()
			defaultConfig.update(config)
			config = defaultConfig
	config["types"] = typeList

	# Resolve all path and make them absolute
	for key in ["assets", "log"]:
		config[key] = os.path.abspath(config[key])

	# Initialize all the classes
	for moduleId, moduleClass in config["pimpl"].items():
		config["pimpl"][moduleId] = moduleClass(config)

	if verbose:
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
	if args.command == "init" and os.path.isdir(config["assets"]):
		shutil.rmtree(config["assets"])

	lib.info("Running command '%s' in '%s'" % (str(args.command), str(config["root"])))
	for moduleId in config["types"]:
		if args.command == "init":
			config["pimpl"][moduleId].init()
		elif args.command == "build":
			config["pimpl"][moduleId].build(args.config, args.target)
		elif args.command == "clean":
			config["pimpl"][moduleId].clean()

"""
Application/command related actions
"""
def commands(args):
	# Read the configuration
	config = readConfig(args)

	idList = args.idList
	lib.info("Executing '%s' on %s" % (args.command, ", ".join(idList)))

	# Start a new command
	if args.command == "start":
		commandsDescs = config["start"]
		if isinstance(commandsDescs, str):
			commandsDescs = [commandsDescs]
		if isinstance(commandsDescs, list):
			commandsDescs = {"default": commandsDescs}

		# Ensure not wrong ID is set
		for commandId in idList:
			if commandId != "all" and commandId not in commandsDescs:
				lib.error("Unknown command preset '%s'" % (commandId))
				sys.exit(1)

		if "all" not in idList:
			commandsDescs = {commandId: commandsDescs[commandId] for commandId in idList}

		for commandId, commandList in commandsDescs.items():
			lib.info("Starting command preset '%s'" % (commandId))
			lib.start(config, commandList)

	elif args.command == "stop":

		for moduleId in config["types"]:
			for appId in idList:
				config["pimpl"][moduleId].stop(None if appId == "all" else appId)

"""
Print information regarding the program and loaded modules
"""
def info(args):

	info = {}
	verbose = not args.json

	# Read the configuration
	config = readConfig(args, verbose)

	# Select what to print
	printAll = False if args.apps else True
	printApps = True if printAll or args.apps else False
	printModules = True if printAll else False

	if printAll:
		info["hash"] = str(getCurrentHash())
		if verbose:
			lib.info("Hash: %s" % (info["hash"]))

	if printModules:
		for moduleId in config["types"]:
			info[moduleId] = config["pimpl"][moduleId].info(verbose)

	if printApps:
		info["statusList"] = []
		for moduleId in config["types"]:
			info["statusList"] += config["pimpl"][moduleId].getStatusList()

		# Print the status list if any
		if verbose and len(info["statusList"]):
			def memoryToStr(memBytes):
				unitIndex = 0
				unitList = ["B", "kB", "MB", "GB", "TB"]
				while memBytes > 768:
					unitIndex += 1
					memBytes /= 1024
				return "%.1f%s" % (memBytes, unitList[unitIndex])
			def uptimeToStr(timeS):
				strList = []
				for check in [[3600 * 24, " day", " days"], [3600, "h", "h"], [60, "m", "m"], [1, "s", "s"]]:
					if timeS >= check[0]:
						unit = int(timeS / check[0])
						strList.append("%i%s" % (unit, check[1] if unit > 1 else check[2]))
						timeS -= unit * check[0]
				return " ".join(strList[:2]) or "0s"

			formatTemplateStr = "%15s%10s%10s%10s%10s%10s%10s %s"
			lib.info("Running applications:")
			lib.info(formatTemplateStr % (
				"Name", "Type", "PID", "Uptime", "CPU %", "Memory", "Restart", "Log"
			))
			for status in info["statusList"]:
				lib.info(formatTemplateStr % (
					status["id"],
					status["type"],
					status["pid"] if "pid" in status else "-",
					uptimeToStr(status["uptime"]) if "uptime" in status else "-",
					status["cpu"] if "cpu" in status else "-",
					memoryToStr(status["memory"]) if "memory" in status else "-",
					status["restart"] if "restart" in status else "-",
					status["log"] if "log" in status else "-"
				))

	# Print the output in JSON format
	if not verbose:
		print(json.dumps(info))

"""
Run the program specified
"""
def run(args):
	# Read the configuration
	config = readConfig(args)

	# Build the list of commands to be executed
	commandList = [shlex.split(cmd) for cmd in args.commandList] + ([args.args] if args.args else [])

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

	verbose = (totalIterations == 1) or args.verbose

	try:
		lib.shellMulti(commandList,
				cwd=".",
				nbIterations=totalIterations,
				isAutoTimeout=isAutoTimeout,
				verbose=verbose,
				timeout=timeout,
				duration=args.duration,
				nbJobs=nbJobs)
	except:
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
			queue = Queue()

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
		"start": commands,
		"stop": commands,
		"run": run,
		"update": update
	}

	parser = argparse.ArgumentParser(description = "Application helper script.")
	parser.add_argument("-c", "--config", action="store", dest="configPath", default=DEFAULT_CONFIG_FILE, help="Path of the build definition (default=%s)." % (DEFAULT_CONFIG_FILE))
	parser.add_argument("-v", "--version", action='version', version="%s hash: %s" % (os.path.basename(__file__), str(getCurrentHash())))

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

	parserInfo = subparsers.add_parser("info", help='Display information about the script and the loaded modules.')
	parserInfo.add_argument("--apps", action="store_true", dest="apps", default=False, help="Display information related to the status of running applications.")
	parserInfo.add_argument("--json", action="store_true", dest="json", default=False, help="Print the output in json format.")

	subparsers.add_parser("init", help='Initialize or setup the project environment.')
	subparsers.add_parser("clean", help='Clean the project environment from build artifacts.')
	parserBuild = subparsers.add_parser("build", help='Build the project.')
	parserBuild.add_argument("-c", "--config", action="store", dest="config", default=None, help="Use this specific build configuration.")
	parserBuild.add_argument('target',  action='store', nargs='?', default=None, help='The target to build. If none, the default target will be built.')

	parserUpdate = subparsers.add_parser("update", help='Update the tool to the latest version available.')
	parserUpdate.add_argument("-f", "--force", action="store_true", dest="force", default=False, help="If set, it will update even if the last version is detected.")

	parserStart = subparsers.add_parser("start", help="Execute a list of predefined commands.")
	parserStart.add_argument('idList',  action='store', nargs='*', default=["default"], help='The command ID to be started. If none, the command ID named "default" will be started.')
	parserStop = subparsers.add_parser("stop", help="Stop the applications associated with the predefined commands.")
	parserStop.add_argument('idList',  action='store', nargs='*', default=["all"], help='The names of the application to be stopped. If none, all applications will be stopped.')

	args = parser.parse_args()

	# Excecute the action
	fct = commandActions.get(args.command, None)
	if fct == None:
		lib.error("Invalid command '%s'" % (str(args.command)))
		parser.print_help()
		sys.exit(1)

	# Execute the proper action
	fct(args)
