#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import argparse
import json
import sys
import os
import imp
import subprocess
import shutil

GIT_REPOSITORY = "https://github.com/blaizard/irbuild.git"
EXECUTABLE_PATH = os.path.realpath(__file__)
EXECUTABLE_DIRECTORY_PATH = os.path.realpath(os.path.dirname(__file__))
EXECUTABLE_NAME = os.path.basename(__file__)
DEPENDENCIES_PATH = "%s/.irbuild" % (EXECUTABLE_DIRECTORY_PATH)
TEMP_DIRECTORY_PATH = "%s/.irbuild-temp" % (EXECUTABLE_DIRECTORY_PATH)

"""
Load the necessary dependencies
"""
def loadDependencies():
	try:
		if not os.path.isdir(DEPENDENCIES_PATH):
			raise Exception("Missing tool dependencies at %s" % (DEPENDENCIES_PATH))
		irbuild = imp.load_module("irbuild", None, DEPENDENCIES_PATH, ('', '', imp.PKG_DIRECTORY))
		if not irbuild:
			raise Exception("Could not load dependencies")
	except Exception as e:
		lib.error("%s, abort." % (e))
		lib.info("Consider updating with '%s update'" % (EXECUTABLE_NAME))
		sys.exit(1)

	# Load the dependencies
	return irbuild.loadModules(), irbuild.getTypeList(), irbuild.lib

"""
Read the configruation file and create it if it does not exists.
"""
def readConfig(path):
	global lib

	# Read the dependencies
	modules, types, lib = loadDependencies()

	config = {
		"types": types,
		"root": os.path.realpath(os.getcwd()),
		"pimpl": {}
	}

	# Read the configuration
	try:
		f = open(path, "r")
		with f:
			try:
				configUser = json.load(f)
				config.update(configUser)
			except Exception as e:
				lib.error("Could not parse configuration file '%s'; %s" % (str(path), str(e)))
				sys.exit(1)
	except IOError:
		lib.warning("Could not open configuration file '%s', using default" % (str(path)))

	# Map and remove unsupported modules
	typeList = []
	for moduleId in config["types"]:
		if moduleId not in modules:
			logError("Module %s is unknown" % (moduleId))
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
def action(command, configPath, *args):
	# Read the configuration
	config = readConfig(configPath)

	lib.info("Running command '%s' in '%s'" % (str(command), str(config["root"])))
	for moduleId in config["types"]:
		if command == "init":
			config["pimpl"][moduleId].init(*args)
		elif command == "build":
			config["pimpl"][moduleId].build(*args)
		elif command == "clean":
			config["pimpl"][moduleId].clean(*args)

"""
Updating the tool
"""
def update(*args):

	# Read the current hash
	currentGitHash = None
	hashPath = os.path.join(DEPENDENCIES_PATH, ".hash")
	if os.path.isfile(hashPath):
		with open(hashPath, "r") as f:
			currentGitHash = f.read()
	lib.info("Current version: %s" % (str(currentGitHash)))

	gitRemote = lib.shell(["git", "ls-remote", "--head", GIT_REPOSITORY], captureStdout=True)
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
		changeList = lib.shell(["git", "log", "--pretty=\"format:%s\"", "%s..HEAD" % (currentGitHash)], cwd=TEMP_DIRECTORY_PATH, captureStdout=True) 

	# These are the location of the files for the updated and should NOT change over time
	executableName = "build.py"
	dependenciesDirectoryName = ".irbuild"

	# Replace the dependencies directory
	if os.path.isdir(DEPENDENCIES_PATH):
		shutil.rmtree(DEPENDENCIES_PATH)
	shutil.move(os.path.join(TEMP_DIRECTORY_PATH, dependenciesDirectoryName), DEPENDENCIES_PATH)

	# Replace main source file
	shutil.move(os.path.join(TEMP_DIRECTORY_PATH, executableName), EXECUTABLE_PATH)

	# Remove temporary directory
	shutil.rmtree(TEMP_DIRECTORY_PATH)

	# Create hash file
	with open(hashPath, "w") as f:
		f.write(gitHash)

	lib.info("Update succeed to %s" % (gitHash))
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
		print "[%s] %s" % (str(type), str(message))

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
	def shell(command, cwd=".", captureStdout=False, ignoreError=False):
		proc = subprocess.Popen(command, cwd=cwd, shell=False, stdout=(subprocess.PIPE if captureStdout else None),
				stderr=(subprocess.PIPE if captureStdout else None))

		output = []
		if proc.stdout:
			for line in iter(proc.stdout.readline, b''):
				line = line.rstrip()
				if captureStdout:
					output.append(line)
				else:
					print line

		out, error = proc.communicate()
		if proc.returncode != 0:
			message = "Fail to execute '%s' in '%s' (errno=%i)" % (" ".join(command), str(cwd), proc.returncode)
			if ignoreError:
				lib.warning(message)
			else:
				raise Exception(message)

		return output

# -----------------------------------------------------------------------------

"""
Entry point fo the script
"""
if __name__ == "__main__":

	commandActions = {
		"init": action,
		"clean": action,
		"build": action,
		"update": update
	}

	parser = argparse.ArgumentParser(description = "Build script.")
	parser.add_argument('command', nargs='?', action="store", default="build", help='Valid commands are "init", (default) "build", "clean".')
	parser.add_argument('--config', action="store", dest="configPath", default=".irbuild.json", help='Path of the build definition.')
	parser.add_argument('args', nargs='*', help='Extra arguments to be passed to the command executed.')
	args = parser.parse_args()

	# Excecute the action
	fct = commandActions.get(args.command, None)
	if fct == None:
		lib.error("Invalid command '%s'" % (str(args.command)))
		parser.print_help()
		sys.exit()

	# Execute the proper action
	fct(args.command, args.configPath, *args.args)
