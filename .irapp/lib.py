#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import subprocess
import sys
import re
import os
import threading
import Queue
import time

# ---- Logging methods --------------------------------------------------------

"""
Print messages
"""
def info(message, type = "INFO"):
	print("[%s] %s" % (str(type), str(message)))

def warning(message):
	info(message, type = "WARNING")

def error(message):
	info(message, type = "ERROR")

# ---- Utility methods --------------------------------------------------------

def which(executable):
	try:
		path = shell(["which", executable], captureStdout=True)
	except:
		return None
	return path[0]

"""
Execute a shell command in a specific directory.
If it fails, it will throw.
"""
def shell(command, cwd=".", captureStdout=False, ignoreError=False, queue=None, signal=None):

	def enqueueOutput(out, queue, signal):
		try:
			for line in iter(out.readline, b''):
				queue.put(line.rstrip().decode('utf-8'))
		except:
			pass
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
				error("Template value '%s' is not set." % (key))
				sys.exit(1)
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
				error("Unsupported type for value '%s'." % (match.group()))
				sys.exit(1)
			return match.group()

		conditionStr = re.sub(self.patternWord, replaceValue, conditionStr)
		condition = eval(conditionStr)
		return bool(condition)

	def process(self, args, removeEmptyLines = True):
		output = self.processInternals(self.template, args)
		output = output.replace("%%", "%")
		if removeEmptyLines:
			output = "\n".join([line for line in output.split('\n') if line.strip() != ''])
		return output

	def processInternals(self, template, args):

		index = 0
		output = ""
		ignoreOutput = 0

		for match in self.pattern.finditer(template):

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

			error("Template operation '%s' is not valid." % (operation))
			sys.exit(1)

		output += template[index:len(template)]
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

	"""
	Runs the initialization of the module.
	"""
	def init(self):
		pass

	def info(self):
		pass

	def clean(self):
		pass

	def build(self, *args):
		pass

	def runPre(self, commandList):
		pass

	def runPost(self, commandList):
		pass

	def deploy(self, *args):
		pass
