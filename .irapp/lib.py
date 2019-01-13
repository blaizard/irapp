#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import subprocess
import sys
import re
import os
import threading
import time
import timeit
import shlex
import codecs
import json
import shutil
import imp
import math
import errno
import stat
try:
	from queue import Queue
except:
	from Queue import Queue

# ---- Local dependencies -----------------------------------------------------

commands = imp.load_source('commands', os.path.join(os.path.dirname(__file__), 'commands.py'))

# ---- Logging methods --------------------------------------------------------

logPrefix = ""

"""
Print messages
"""
def info(message):
	sys.stdout.write("%s[INFO] %s\n" % (str(logPrefix), str(message)))
	sys.stdout.flush()

def warning(message):
	sys.stdout.write("%s[WARNING] %s\n" % (str(logPrefix), str(message)))
	sys.stdout.flush()

def error(message):
	sys.stderr.write("%s[ERROR] %s\n" % (str(logPrefix), str(message)))
	sys.stderr.flush()

def fatal(message):
	sys.stderr.write("%s[FATAL] %s\n" % (str(logPrefix), str(message)))
	sys.stderr.flush()
	sys.exit(1)

# ---- Commands related -------------------------------------------------------

"""
Start a list of commands
"""
def start(config, commandList):
	# Context fo the command
	context = {
		"cwd": config["root"]
	}

	for command in commandList:
		argList = shlex.split(command)

		# Command from module
		if argList[0] in config["pimpl"]:
			if len(argList) < 3:
				raise Exception("Too few arguments for command '%s'" % (command))
			config["pimpl"][argList[0]].start(argList[1], argList[2:], context)
		# Pre-built command
		else:
			commandExec = getattr(commands.Commands, argList[0], None)
			if commandExec:
				commandExec(context, argList[1:])
			# Else an error occured
			else:
				raise Exception("Unknown command '%s'" % (command))

# ---- Utility methods --------------------------------------------------------

"""
Generates a unique ID: an integer starting from 1
"""
class UniqueId:
	counter = 0
def uniqueId():
	UniqueId.counter += 1
	return UniqueId.counter

"""
Delete a directory and all its content
"""
def rmtree(path):
	# This is needed for Windows
	def handleRemoveReadonly(func, path, exc):
		excvalue = exc[1]
		if excvalue.errno == errno.EACCES:
			os.chmod(path, stat.S_IRWXU | stat.S_IRWXG | stat.S_IRWXO) # 0777
			func(path)
		else:
			raise
	retryCounter = 3
	while retryCounter:
		shutil.rmtree(path, ignore_errors=True, onerror=handleRemoveReadonly)
		if not os.path.exists(path):
			break
		retryCounter -= 1
		# Wait for 1s, this is needed for Windows (probably for some cache to be flushed)
		time.sleep(1)
	if retryCounter == 0:
		fatal("Unable to delete directory '%s'" % (str(path)))

"""
Extract the version number from the output received by a shell command
"""
def getVersion(output):
	for line in output:
		match = re.search(r'(\d+(?:\.\d+)+)', line)
		if match:
			return match.group(1)
	return "unknown"

"""
Deep merge 2 dictionaries
"""
def deepMerge(dst, src):
	for key, value in src.items():
		if isinstance(value, dict):
			node = dst.setdefault(key, {})
			deepMerge(node, value)
		elif isinstance(value, list):
			node = dst.setdefault(key, [])
			node += value
		else:
			dst[key] = value

	return dst

"""
Ensure the proper format of the configuration
"""
def configSanityCheck(config, user=False):

	def assertTypes(config, key, typeList, example):
		"""
		Assert that the iterable value passed into argument is of the types specified
		"""
		def assertTypesInternal(values, typeList):
			# Handle the case where str can be unicode and since there is a major difference between python2 and 3,
			# it needs to be addressed with basestring or str
			if typeList[0] == str:
				if not isinstance(values, basestring if sys.version_info.major == 2 else str):
					return False
			elif not isinstance(values, typeList[0]):
				return False

			if len(typeList) > 1:
				if isinstance(values, dict):
					for key, value in values.items():
						if not assertTypesInternal(key, [str]) or not assertTypesInternal(value, typeList[1:]):
							return False
				elif isinstance(values, list):
					for value in values:
						if not assertTypesInternal(value, typeList[1:]):
							return False
			return True

		if key in config:
			if not assertTypesInternal(config[key], typeList):
				raise Exception("The configuration {... \"%s\": %s ...} is not of valid format, it should be of type %s; for example: {... \"%s\": %s ...}" % (
						key, json.dumps(config[key]), "::".join([t.__name__ for t in typeList]), key, json.dumps(example)))

	if not isinstance(config, dict):
		raise Exception("Configuration must be a dictionary: %s" % (str(config)))

	if user:
		for key in ["lib", "root", "pimpl"]:
			if key in config:
				raise Exception("The configuration key '%s' is protected and cannot be altered" % (key))

	assertTypes(config, "parallelism", [int], 4)
	assertTypes(config, "types", [list, str], ["python", "cmake"])
	assertTypes(config, "start", [dict, list, str], {"server": ["cd server/bin", "daemon server ./main"]})
	assertTypes(config, "dependencies", [dict, list, str], {"debian": ["libssl-dev", "libcurl-dev"]})
	assertTypes(config, "tests", [dict, list, str], {"gtest": ["build/bin/tests"], "python.unittest": ["tests/testSimple.py"]})
	assertTypes(config, "builds", [dict, dict], {"gcc-release": {"compiler": "gcc", "lint": True}})
	assertTypes(config, "templates", [dict, dict, str], {"debian": {"run": "./%path%"}})
	assertTypes(config, "ignore", [list, str], ["git.ignore.irapp"])
	assertTypes(config, "dispatch", [list, str], ["./relative/path/to/project1"])

"""
Return the specific command based on the attributes and the global configuration
"""
def getCommand(config, commandType, typeIds, args):
	# Build the description from the typeIds
	desc = {}
	desc.update(config)
	for typeId in typeIds.split("."):
		if typeId in config["templates"]:
			desc.update(config["templates"][typeId])

	if commandType not in desc:
		return None
	templateStr = desc[commandType]

	# Add the custom arguments
	desc.update(args)
	return Template(templateStr).process(desc, recursive=True, removeEmptyLines=False)

"""
Return the path of the executable if available, None otherwise
"""
def which(executable, cwd="."):
	# If the path is relative, returns the full path
	firstSep = executable.find(os.path.sep)
	if firstSep > 0:
		return os.path.normpath(os.path.join(cwd, executable))
	elif firstSep == 0:
		return executable

	try:
		if sys.platform =='win32':
			for root in os.environ['PATH'].split(os.pathsep):
				for ext in [".exe", ".cmd", ""]:
					executablePath = os.path.join(root, executable + ext)
					if os.path.isfile(executablePath):
						return executablePath
		else:
			return shell(["which", executable], capture=True)[0]
	except:
		pass
	return None

"""
To store the instance of process started with the non-blocking option
"""
runningProcess = []

"""
Execute a shell command in a specific directory.
If it fails, it will throw.
@param blocking Tells if the process should block the execution. If not it will run in parallel and might block the ending of the caller
                process if it ends.
"""
def shell(command, cwd=".", capture=False, ignoreError=False, queue=None, signal=None, hideStdout=False, hideStderr=False, blocking=True):

	def enqueueOutput(out, queue, signal):
		try:
			for line in iter(out.readline, b''):
				queue.put(line.rstrip().decode('utf-8', 'ignore'))
		except:
			pass
		out.close()
		signal.set()

	stdout = open(os.devnull, 'w') if hideStdout else (subprocess.PIPE if capture or queue else None)
	stderr = open(os.devnull, 'w') if hideStderr else (subprocess.STDOUT if capture or queue else None)

	isReturnStdout = True if capture and not queue else False

	# Workaround on Windows machine, the environment path is not searched to find the executable, hence
	# we need to do this manually.
	if sys.platform =='win32':
		fullPath = which(command[0], cwd=cwd)
		if fullPath:
			command[0] = fullPath

	proc = subprocess.Popen(command, cwd=cwd, shell=False, stdout=stdout, stderr=stderr)

	# If non-blocking returns directly
	if not blocking:
		runningProcess.append(proc)
		return

	if not queue:
		queue = Queue()

	if not signal:
		signal = threading.Event()

	# Wait until a signal is raised or until the the process is terminated
	if capture:
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
	stoppedBySignal = True if proc.poll() is None else False
	if stoppedBySignal:
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

	if not stoppedBySignal and proc.returncode != 0:
		errorMsgList.append("return.code=%s" % (str(proc.returncode)))

	if len(errorMsgList):
		if not ignoreError:
			message = "Failed to execute '%s' in '%s': %s" % (" ".join(command), str(cwd), ", ".join(errorMsgList))
			raise Exception(message)

	# Build the output list
	return list(queue.queue) if isReturnStdout else []

"""
Execute multiple commands, either sequentially or in parallel.
It supports a limited number of iterations, of time or other options.

@param nbIterations Total number of iteration of the commandList before terminating. If 0, it will be endless.
@param isAutoTimeout If set, it will automatically calculate a timeout for each iteration, this timeout is based on previous run.
"""
def shellMulti(commandList, cwd=".", nbIterations=1, isAutoTimeout=True, verbose=True, verboseCommand=False, timeout=0, duration=0, nbJobs=1, hideStdout=False, hideStderr=False, ignoreError=False):

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

	# Create the pool of workers
	workerList = [None] * nbJobs
	workerContext = [None] * nbJobs
	workerErrors = {}

	startingTime = timeit.default_timer()
	startingTimeIteration = timeit.default_timer()
	totalTimeS = 0
	curNbIterations = 0
	nbWorkers = 0
	commandIndex = 0
	curIteration = 0
	iterations = {}
	errorMsg = None

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
							curNbIterations += 1
							totalTimeS += iterations[workerIteration]["time"]
							startingTimeIteration = timeit.default_timer()
							iterations.pop(workerIteration)
					else:
						nbWorkers += 1

				# If not registered, add it
				if not workerList[i] and (nbIterations == 0 or curIteration < nbIterations):
					workerContext[i] = Queue()
					signal = threading.Event()
					workerList[i] = {
						"command": " ".join(commandList[commandIndex]),
						"worker": Thread(target=shell, args=(commandList[commandIndex], cwd, (not verbose), ignoreError, None if verbose else workerContext[i], signal, hideStdout, hideStderr)),
						"time": timeit.default_timer(),
						"iterationId": curIteration,
						"signal": signal
					}
					if verboseCommand:
						info("Executing %s" % (workerList[i]["command"]))
					workerList[i]["worker"].start()
					# Increase the command index and the interation
					commandIndex += 1
					if commandIndex == len(commandList):
						commandIndex = 0
						curIteration += 1
					nbWorkers += 1

			if not verbose:
				sys.stdout.write("\rTime: %.4fs, %i iteration(s), average %s, timeout %s, %i job(s)" % (
						(timeit.default_timer() - startingTime),
						curNbIterations,
						str(float("%.6f" % (totalTimeS / curNbIterations))) + "s" if curNbIterations else "?",
						("%is" % (timeout)) if timeout else "-",
						nbWorkers))
				sys.stdout.flush()

			# Update the timeout, if auto timeout is selected
			if isAutoTimeout and curNbIterations:
				timeout = math.ceil(totalTimeS / curNbIterations * 5)

			# If time reached its limit, break
			if duration and (timeit.default_timer() - startingTime) > duration:
				break

			# If the number of iterations reached its limit, break
			if nbIterations and (curNbIterations >= nbIterations):
				break

	except (KeyboardInterrupt, SystemExit) as e:
		errorMsg = "<<<< Keyboard Interrupt >>>>"
	except BaseException as e:
		errorMsg = str(e)

	# Print the error message if any
	if not verbose:
		print("")
	if errorMsg:
		error(errorMsg)

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
				error("---- (worker #%i) -------------------------------------------------------------" % (i))
				for line in list(workerContext[i].queue):
					print(line)
				error("Failure cause: %s" % (", ".join(errorList)))
		raise Exception()

"""
Ensure that the processes previously started are destroyed
"""
def destroy():
	# Wait until all non-blocking process previously started are done
	for process in runningProcess:
		process.wait()

# ---- Log related methods ----------------------------------------------------

# Hack
codecs.register_error("strict", codecs.ignore_errors)

"""
Rotating log
"""
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
			self.curLog = codecs.open(self.getLogPath(self.curLogIndex), "w", encoding="utf-8")
			self.curLogSize = 0

		self.curLog.write(message)
		self.curLog.flush()
		self.curLogSize += len(message)

"""
Application log factory
"""
class LogFactory:
	def __init__(self, logDirectory, appId, runningPidList, maxLogs=10, maxLogSizeBytes=100 * 1024):
		self.logDirPath = os.path.join(logDirectory, appId)
		self.restart = -1
		self.maxLogs = maxLogs
		self.maxLogSizeBytes = maxLogSizeBytes

		# Remove logs from all non-running apps
		if os.path.exists(self.logDirPath):
			runningPidList = [str(pid) for pid in runningPidList]
			for file in os.listdir(self.logDirPath):
				filePath = os.path.join(self.logDirPath, file)
				if os.path.isdir(filePath) and file not in runningPidList:
					rmtree(filePath)

	@staticmethod
	def getMetadata(*path):
		metadataPath = os.path.join(os.path.join(*path), ".irapp.application.json")
		metadata = {}
		if os.path.exists(metadataPath):
			with open(metadataPath, "r") as f:
				try:
					metadata = json.load(f)
				except:
					pass
		return (metadata, metadataPath)

	def createLogs(self, pid):

		self.restart += 1

		# Create log directory entry and remove its content
		curlogDirPath = os.path.join(self.logDirPath, str(pid))
		if os.path.exists(curlogDirPath):
			rmtree(curlogDirPath)
		os.makedirs(curlogDirPath)

		# Update the json file
		metadata, metadataPath = LogFactory.getMetadata(curlogDirPath)
		metadata.update({
			"restart": self.restart,
			"time": time.time()
		})
		with open(metadataPath, "w") as f:
			json.dump(metadata, f)

		return (RotatingLog(curlogDirPath, "stdout", maxLogs=self.maxLogs, maxLogSizeBytes=self.maxLogSizeBytes),
				RotatingLog(curlogDirPath, "stderr", maxLogs=self.maxLogs, maxLogSizeBytes=self.maxLogSizeBytes))

"""
Process a template with specific values.

All %<action>% are processed, where action can be:
- if <condition>: Process the following if block (ending with % end %)
                   only if the condition evaluates to True
- for <variable> in <identifier>: Run the block (ending with % end %)
                                  as many tim eas there are entries
All strings %% are replace with %
"""
class Template:
	def __init__(self, template):
		self.template = template

		# Pre-process regexpr
		self.pattern = re.compile("%([^%]+)%")
		self.patternIf = re.compile("^if\s+([^\%]+)$")
		self.patternFor = re.compile("^for\s+([^\s]+)\s+in\s+([^\s]+)$")
		self.patternForIndex = re.compile("^for\s+([^\s]+)\s*,\s*([^\s]+)\s+in\s+([^\s]+)$")
		self.patternSet = re.compile("^[^\s]+$")
		self.patternEnd = re.compile("^end$")
		self.patternWord = re.compile("[^\s]+")

	def getValue(self, args, key):

		for k in key.split("."):
			if k not in args:
				fatal("Template value '%s' is not set." % (key))
			args = args[k]() if callable(args[k]) else args[k]

		return args

	def evalCondition(self, args, conditionStr):

		def replaceValue(match):
			if match.group() not in ["and", "or", "not", "(", ")"]:
				value = args
				for k in match.group().split("."):
					if k not in value:
						return match.group()
					value = value[k]
				# Replace the value
				if isinstance(value, bool):
					return str(value)
				elif isinstance(value, str):
					return "\"%s\"" % (value)
				elif isinstance(value, list):
					return str(bool(value))
				elif isinstance(value, dict):
					return str(bool(value))
				fatal("Unsupported type for value '%s'." % (match.group()))
			return match.group()

		conditionStr = re.sub(self.patternWord, replaceValue, conditionStr)
		try:
			condition = eval(conditionStr)
		except:
			fatal("Cannot evaluate condition '%s'" % (conditionStr))
		return bool(condition)

	def process(self, args, removeEmptyLines=True, recursive=False):
		processedTemplate = self.template

		# Process the template
		nbIterations = 0
		while True:
			processedTemplate, isProcessed = self.processInternals(processedTemplate, args)
			if not isProcessed or not recursive:
				break
			nbIterations += 1
			if nbIterations > 10:
				raise Exception("Too many iterations (>10)")

		processedTemplate = processedTemplate.replace("%%", "%")
		if removeEmptyLines:
			processedTemplate = "\n".join([line for line in processedTemplate.split('\n') if line.strip() != ''])
		return processedTemplate

	def processInternals(self, template, args):

		index = 0
		output = ""
		ignoreOutput = 0
		isProcessed = False

		for match in self.pattern.finditer(template):

			# Tells that at least something has been done
			isProcessed = True

			# Update the output string and the new index
			if not ignoreOutput:
				output += template[index:match.start()]
			index = match.end()

			# Identify the operation
			operation = match.group(1).strip()

			# If block
			match = self.patternIf.match(operation)
			if match:
				if (not ignoreOutput) and self.evalCondition(args, match.group(1)):
					output += self.processInternals(template[index:len(template)], args)
				ignoreOutput += 1
				continue

			# For loop
			match = self.patternFor.match(operation)
			if match:
				if not ignoreOutput:
					for value in self.getValue(args, match.group(2)):
						args[match.group(1)] = value
						output += self.processInternals(template[index:len(template)], args)
						del args[match.group(1)]

				ignoreOutput += 1
				continue

			# For loop with index
			match = self.patternForIndex.match(operation)
			if match:
				if not ignoreOutput:
					valueObject = self.getValue(args, match.group(3))
					if isinstance(valueObject, list):
						iterator = enumerate(valueObject)
					else:
						iterator = valueObject.items()
					for key, value in iterator:
						args[match.group(1)] = str(key)
						args[match.group(2)] = value
						output += self.processInternals(template[index:len(template)], args)
						del args[match.group(2)]
						del args[match.group(1)]

				ignoreOutput += 1
				continue

			# End pattern
			match = self.patternEnd.match(operation)
			if match:
				if not ignoreOutput:
					return output
				ignoreOutput -= 1
				continue

			# Set value
			match = self.patternSet.match(operation)
			if match:
				if not ignoreOutput:
					output += str(self.getValue(args, match.group(0)))
				continue

			fatal("Template operation '%s' is not valid." % (operation))

		output += template[index:len(template)]
		return (output, isProcessed)

# ---- Module base class ------------------------------------------------------

"""
Defines modules supported. Each modules defines a certain set of optional
functions.
"""
class Module:

	def __init__(self, config):
		self.config = config
		self.defaultBuildType = None

	@classmethod
	def name(cls):
		return cls.__name__.lower()

	"""
	Defines whether or not a module is present.
	Returns True if the module is present, False otherwise.
	"""
	@staticmethod
	def check(config):
		return False

	"""
	Return the default configuration of the module.
	"""
	@staticmethod
	def config():
		return {}

	"""
	Get the configuration value for this modules.
	The rule is, first look in to the specific values (aka: config["git"][...] for example)
	if nothing is found, look in the global config (aka: config[...])
	if nothing is found return the default value from the specific values if set, otherwise the default
	"""
	def getConfig(self, keyList=[], default=None, onlySpecific=False):
		def getValue(config):
			for key in keyList:
				if key not in config:
					return None
				config = config[key]
			return config
		value = getValue(self.config[self.name()]) if self.name() in self.config else None
		# If there is no specific value, look for the global value
		if value == None and not onlySpecific:
			value = getValue(self.config)
		# Return the value if there is one
		if value:
			return value
		# If the default value is set, return it, otherwise return the default from the specific config
		return getValue(self.__class__.config()) if default == None else default

	"""
	Asses if a confguration is ignored or not
	"""
	def isIgnore(self, *keys):
		ignoreDict = self.config["ignoreDict"]
		for key in [self.name()] + list(keys):
			if key in ignoreDict:
				if isinstance(ignoreDict[key], bool):
					return True
				ignoreDict = ignoreDict[key]
		return False

	"""
	Generates a log factory, used to create logs for an application
	"""
	def logFactory(self, appId, runningPidList):
		return LogFactory(self.config["log"], appId, runningPidList)

	"""
	Return the path of an existing asset for read-only
	"""
	def getAssetPath(self, *name):
		path = os.path.join(os.path.realpath(os.path.dirname(__file__)), "templates", *name)
		if not os.path.exists(path):
			raise Exception("There is no assets at %s" % (path))
		return path

	"""
	Save an asset from a buffer and returns its path
	relative to the root directory
	"""
	def publishAsset(self, content, *name):
		return self.publishAssetTo(content, self.config["assets"], *name)

	def publishAssetTo(self, content, directory, *name):
		path = os.path.join(directory, *name)
		# Create the directory path 
		if not os.path.exists(os.path.dirname(path)):
			os.makedirs(os.path.dirname(path))
		# Create the file
		with open(path, "w") as f:
			f.write(content)
		info("Published asset to '%s'" % (path))
		return os.path.relpath(path, self.config["root"])

	"""
	Copy an asset and returns its path relative to the root directory
	"""
	def copyAsset(self, *name):
		return self.copyAssetTo(self.config["assets"], *name)

	def copyAssetTo(self, directory, *name):
		path = self.getAssetPath(*name)
		with open(path, "r") as f:
			content = f.read()
		return self.publishAssetTo(content, directory, *name)

	def getStatusList(self):
		statusList = self.status() or [];
		for status in statusList:
			if "pid" in status:
				metadata, metadataPath = LogFactory.getMetadata(self.config["log"], status["id"], str(status["pid"]))
				if "time" in metadata and "restart" in metadata:
					status["uptime"] = time.time() - metadata["time"]
					status["restart"] = metadata["restart"]
					status["log"] = os.path.dirname(metadataPath)
			status["type"] = self.__class__.__name__.lower()
		return statusList

	"""
	Save and set the default build type, if valid
	"""
	def setDefaultBuildType(self, buildType, save=True):
		# Check if the build type is registered in the config of this module
		if not self.getConfig(["builds", buildType], default=False, onlySpecific=True):
			return False

		# If build type is different than previous one already registered, then cleanup
		if save:
			currentBuildType = self.getDefaultBuildType(onlyFromConfig=True)
			if buildType != currentBuildType:
				self.clean()
				info("Setting '%s' as default build configuration for '%s'" % (buildType, self.name()))
				currentBuildTypePath = os.path.join(self.config["artifacts"], ".%s.buildtype" % (self.name()))
				with open(currentBuildTypePath, "w") as f:
					f.write(buildType)
		self.defaultBuildType = buildType
		return True

	"""
	Return the current active build type
	"""
	def getDefaultBuildType(self, onlyFromConfig=False):

		# If the configuration is present
		if self.defaultBuildType:
			return self.defaultBuildType

		# Read the current configuration if any
		currentBuildTypePath = os.path.join(self.config["artifacts"], ".%s.buildtype" % (self.name()))
		if os.path.isfile(currentBuildTypePath):
			with open(currentBuildTypePath, "r") as f:
				buildType = f.read()
				if self.getConfig(["builds", buildType], default=False, onlySpecific=True):
					self.defaultBuildType = buildType
					return buildType

		# If none, use the first config
		if not onlyFromConfig and "builds" in self.__class__.config():
			for name in self.getConfig(["builds"], default={}, onlySpecific=True):
				if self.getConfig(["builds", name, "default"], default=False, onlySpecific=True):
					return name

		return None

	"""
	Return the default build
	"""
	def getDefaultBuild(self):
		buildType = self.getDefaultBuildType()
		return self.getConfig(["builds", buildType], default={}, onlySpecific=True)

	"""
	Runs the initialization of the module.
	"""
	def init(self):
		pass

	def info(self, verbose):
		pass

	def clean(self):
		pass

	def build(self, target):
		pass

	def runPre(self, commandList):
		pass

	def runPost(self, commandList):
		pass

	"""
	Start application.
	"""
	def start(self, *args):
		pass

	"""
	Stop all application refered by appId. If appId is None, stop all applications.
	"""
	def stop(self, appId=None):
		pass

	# Application statuses
	def status(self):
		pass
