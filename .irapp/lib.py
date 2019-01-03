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

try:
	from queue import Queue
except:
	from Queue import Queue

# ---- Local dependencies -----------------------------------------------------

commands = imp.load_source('commands', os.path.join(os.path.dirname(__file__), 'commands.py'))
types = imp.load_source('types', os.path.join(os.path.dirname(__file__), 'types.py'))

# ---- Logging methods --------------------------------------------------------

"""
Print messages
"""
def info(message):
	sys.stdout.write("[INFO] %s\n" % (str(message)))
	sys.stdout.flush()

def warning(message):
	sys.stdout.write("[WARNING] %s\n" % (str(message)))
	sys.stdout.flush()

def error(message):
	sys.stderr.write("[ERROR] %s\n" % (str(message)))
	sys.stderr.flush()

def fatal(message):
	sys.stderr.write("[FATAL] %s\n" % (str(message)))
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
Deep merge 2 dictionaries
"""
def deepMerge(dst, src):
	for key, value in src.items():
		if isinstance(value, dict):
			node = dst.setdefault(key, {})
			deepMerge(node, value)
		else:
			dst[key] = value

	return dst

"""
Return the path of the executable if availabl, None otherwise
"""
def which(executable):
	try:
		path = shell(["which", executable], capture=True)
	except:
		return None
	return path[0]

"""
Execute a shell command in a specific directory.
If it fails, it will throw.
"""
def shell(command, cwd=".", capture=False, ignoreError=False, queue=None, signal=None, hideStdout=False, hideStderr=False):

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

	proc = subprocess.Popen(command, cwd=cwd, shell=False, stdout=stdout, stderr=stderr)

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
		message = "Failed to execute '%s' in '%s': %s" % (" ".join(command), str(cwd), ", ".join(errorMsgList))
		if ignoreError:
			warning(message)
		else:
			raise Exception(message)

	# Build the output list
	return list(queue.queue) if isReturnStdout else []

"""
Execute multiple commands, either sequentially or in parallel.
It supports a limited number of iterations, of time or other options.

@param nbIterations Total number of iteration of the commandList before terminating. If 0, it will be endless.
@param isAutoTimeout If set, it will automatically calculate a timeout for each iteration, this timeout is based on previous run.
"""
def shellMulti(commandList, cwd=".", nbIterations=1, isAutoTimeout=True, verbose=True, verboseCommand=False, timeout=0, duration=0, nbJobs=1, hideStdout=False, hideStderr=False):

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
						"worker": Thread(target=shell, args=(commandList[commandIndex], cwd, (not verbose), False, None if verbose else workerContext[i], signal, hideStdout, hideStderr)),
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
					shutil.rmtree(filePath)

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
			shutil.rmtree(curlogDirPath)
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
			args = args[k]

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
	Return the specific command based on the attributes
	"""
	def getCommand(self, commandType, typeIds, args):
		# Build the description from the typeIds
		desc = {"run": "./%path%"}
		for typeId in typeIds.split("."):
			if typeId in self.config["pimpl"]:
				desc.update(self.config["pimpl"][typeId].getCommandsTemplate())
			elif typeId in types.Types:
				desc.update(types.Types[typeId])

		if commandType not in desc:
			return None
		templateStr = desc[commandType]
		desc.update(args)
		return Template(templateStr).process(desc, recursive=True, removeEmptyLines=False)

	"""
	Get the configuration value for this modules.
	Start to look in the specific values, if not, look in the generic.
	If no value is present, returns noneValue
	"""
	def getConfig(self, keyList=[], noneValue=None, onlySpecific=False):
		def getValue(config):
			for key in keyList:
				if key not in config:
					return None
				config = config[key]
			return config
		# Look for the specific option first
		specificValue = getValue(self.config[self.name()]) if self.name() in self.config else None
		# Then the generic
		genericValue = getValue(self.__class__.config()) if onlySpecific else getValue(self.config)
		# Merge the values
		if isinstance(genericValue, dict) and isinstance(specificValue, dict):
			return self.config["lib"].deepMerge(genericValue, specificValue)
		if specificValue != None:
			return specificValue
		if genericValue != None:
			return genericValue
		return noneValue

	"""
	Check if a configruation is available
	"""
	def isConfig(self, keyList=[], onlySpecific=False):
		return False if self.getConfig(keyList, onlySpecific=onlySpecific) == None else True

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
		if not self.isConfig(["builds", buildType], onlySpecific=True):
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
				if buildType in self.config["builds"]:
					self.defaultBuildType = buildType
					return buildType

		# If none, use the first config
		if not onlyFromConfig:
			for name in self.config["builds"]:
				return name

		return None

	"""
	Return the dependencies of this specific module per platform
	"""
	def dependencies(self):
		return {}

	"""
	Command invocation template
	"""
	def getCommandsTemplate(self):
		return {}

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
