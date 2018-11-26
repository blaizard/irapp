#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import re

class CMake(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isfile(os.path.join(config["root"], "CMakeLists.txt"))

	@staticmethod
	def config():
		if lib.which("ninja"):
			generator = "Ninja"
		else:
			generator = "Unix Makefiles"

		return {
			"buildDir": "build",
			"buildConfigs": {
				"gcc-debug": {
					"type": "Debug",
					"compiler": "gcc",
					"default": True
				},
				"gcc-coverage": {
					"type": "Debug",
					"compiler": "gcc",
					"coverage": True
				},
				"gcc-release": {
					"type": "Release",
					"compiler": "gcc"
				},
				"clang-debug": {
					"type": "Debug",
					"compiler": "clang"
				},
				"clang-release": {
					"type": "Release",
					"compiler": "clang"
				}
			},
			"buildGenerator": generator,
			"staticAnalyzerIgnore": [],
		}

	"""
	Save the default build type
	"""
	def setDefaultBuildType(self, buildType):
		currentBuildTypePath = os.path.join(self.config["root"], self.config["buildDir"], ".buildtype")

		lib.info("Setting '%s' as default build configuration" % (buildType))
		with open(currentBuildTypePath, "w") as f:
			f.write(buildType)

	"""
	Return the current active build type
	"""
	def getDefaultBuildType(self, onlyFromConfig=False):
		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])
		currentBuildTypePath = os.path.join(buildDirPath, ".buildtype")

		# Read the current configuration if any
		if os.path.isfile(currentBuildTypePath):
			with open(currentBuildTypePath, "r") as f:
				buildType = f.read()
				if buildType in self.config["buildConfigs"]:
					return buildType

		# If none, use the first config
		if not onlyFromConfig:
			for name in self.config["buildConfigs"]:
				return name

		return None

	def hasCoverage(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return ("coverage" in self.config["buildConfigs"][buildType]) and (self.config["buildConfigs"][buildType]["coverage"])

	def getType(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.config["buildConfigs"][buildType]["type"] if ("type" in self.config["buildConfigs"][buildType]) else "Debug"

	def getCompiler(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.config["buildConfigs"][buildType]["compiler"] if ("compiler" in self.config["buildConfigs"][buildType]) else "gcc"

	def init(self):

		# Print cmake version
		cmakeVersion = lib.shell(["cmake", "--version"], captureStdout=True)
		lib.info("CMake version: %s" % (re.search(r'([\d.]+)', cmakeVersion[0]).group(1)))

		# Removing CMake build directory
		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])
		lib.info("Cleanup CMake build directory at '%s'" % (buildDirPath))
		# Try to cleanup the build directory, not critical if it fails
		lib.shell(["rm", "-rfd", os.path.basename(self.config["buildDir"])], cwd=os.path.dirname(buildDirPath), ignoreError=True)
		lib.shell(["mkdir", os.path.basename(self.config["buildDir"])], cwd=os.path.dirname(buildDirPath), ignoreError=True)

		# Remove all CMakeCache.txt if existing
		for root, dirs, files in os.walk(self.config["root"]):
			for file in files:
				if file == "CMakeCache.txt":
					os.remove(os.path.join(root, file))

		# Initialize CMake configurations
		defaultBuildType = None
		firstValidBuild = None
		for name, buildConfig in self.config["buildConfigs"].items():

			# Set default values and update the build config
			updatedBuildConfig = {
				"type": self.getType(name),
				"compiler": self.getCompiler(name),
				"coverage": self.hasCoverage(name),
				"default": False,
				"available": False
			}
			updatedBuildConfig.update(buildConfig)
			self.config["buildConfigs"][name] = updatedBuildConfig

			# Set the command
			commandList = ["cmake", "-G", self.config["buildGenerator"], "-DCMAKE_BUILD_TYPE=%s" % (updatedBuildConfig["type"])]

			# ---- Compiler specific options ----------------------------------

			# Identify the compiler and ensure it is present
			isCoverageError = False

			# ---- GCC
			if updatedBuildConfig["compiler"] == "gcc":
				cCompiler = lib.which("gcc")
				cxxCompiler = lib.which("g++")
				if updatedBuildConfig["coverage"]:
					if lib.which("lcov"):
						self.copyAssetTo(".", ".lcovrc")
						commandList.extend(["-DCMAKE_CXX_FLAGS=--coverage", "-DCMAKE_C_FLAGS=--coverage"])
					else:
						isCoverageError = True

			# ---- CLANG
			elif updatedBuildConfig["compiler"] == "clang":
				cCompiler = lib.which("clang")
				cxxCompiler = lib.which("clang++")
				if updatedBuildConfig["coverage"]:
					isCoverageError = True

			else:
				lib.error("Unkown compiler '%s' for build configuration '%s'" % (str(updatedBuildConfig["compiler"]), name))
				sys.exit(1)

			if isCoverageError:
				lib.warning("Unable to find coverage tools for '%s', ignoring configuration '%s'" % (updatedBuildConfig["compiler"], name))
				continue

			if not cCompiler or not cxxCompiler:
				lib.warning("Unable to find compiler for '%s', ignoring configuration '%s'" % (updatedBuildConfig["compiler"], name))
				continue

			# Add the compilers
			commandList.extend(["-DCMAKE_C_COMPILER=%s" % (cCompiler), "-DCMAKE_CXX_COMPILER=%s" % (cxxCompiler)])

			# -----------------------------------------------------------------

			# Mark the configuration as available if it is for this platform
			self.config["buildConfigs"][name]["available"] = True

			lib.info("Initializing build configuration '%s' with generator '%s'" % (name, str(self.config["buildGenerator"])))
			lib.shell(["mkdir", "-p", name], cwd=buildDirPath)
			buildTypePath = os.path.join(buildDirPath, name)

			commandList.append("../..")
			lib.shell(commandList, cwd=buildTypePath)

			# Set the default build if any is set
			if updatedBuildConfig["default"]:
				self.setDefaultBuildType(name)
				defaultBuildType = name

			# Save the first valid build to identify if any build has been processed
			if not firstValidBuild:
				firstValidBuild = name

		if not firstValidBuild:
			lib.error("No build configuration has been set.")
			sys.exit(1)
		# Set the defautl build if none explicitly defined
		elif not defaultBuildType:
			self.setDefaultBuildType(firstValidBuild)
			self.config["buildConfigs"][firstValidBuild]["default"] = True

	def clean(self):

		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])
		lib.info("Cleaning %s" % (buildDirPath))
		lib.shell(["rm", "-rfd", os.path.join(buildDirPath, "bin")], cwd=self.config["root"])
		lib.shell(["rm", "-rfd", os.path.join(buildDirPath, "lib")], cwd=self.config["root"])
		lib.shell(["mkdir", os.path.join(buildDirPath, "bin")], cwd=self.config["root"])
		lib.shell(["mkdir", os.path.join(buildDirPath, "lib")], cwd=self.config["root"])

	def build(self, buildType = None, *args):

		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])

		# Read the current configuration if any
		currentBuildType = self.getDefaultBuildType(onlyFromConfig=True)

		# Identifying the defautl build type if not explicitly set
		if buildType == None:
			buildType = self.getDefaultBuildType()

		lib.info("Building configuration: %s" % (buildType))

		# If the build type is different then clean the directory
		if buildType != currentBuildType:
			self.clean()
			self.setDefaultBuildType(buildType)

		lib.shell(["cmake", "--build", os.path.join(buildDirPath, buildType), "--", "-j3"], cwd=self.config["root"])

	def info(self, *args):

		defaultBuildType = self.getDefaultBuildType()
		buildDir = os.path.join(self.config["root"], self.config["buildDir"])
		lib.info("Build configurations (using '%s'):" % (self.config["buildGenerator"]))
		for buildType, buildConfig in self.config["buildConfigs"].items():
			# Check if available
			buildPath = os.path.join(buildDir, buildType)
			buildPath = buildPath if os.path.isdir(buildPath) else ""

			isDefaultBuildType = "(default)" if defaultBuildType == buildType else ""
			hasCoverage = "(coverage)" if self.hasCoverage(buildType) else ""

			lib.info("%20s %9s %8s %8s %10s %s" % (buildType, isDefaultBuildType, self.getType(buildType), self.getCompiler(buildType), hasCoverage, str(buildPath)))

	def runPre(self, *args):

		buildType = self.getDefaultBuildType()
		if self.hasCoverage(buildType):

			lib.info("Preparing coverage run")
			lcovVersion = lib.shell(["lcov", "--version"], captureStdout=True)
			lib.info("lcov version: %s" % (re.search(r'([\d.]+)', lcovVersion[0]).group(1)))
			gcovVersion = lib.shell(["gcov", "--version"], captureStdout=True)
			lib.info("gcov version: %s" % (re.search(r'([\d.]+)', gcovVersion[0]).group(1)))

			# Clean-up directory by removing all previous gcda files
			buildDir = os.path.join(self.config["root"], self.config["buildDir"], buildType)
			for root, dirs, files in os.walk(buildDir):
				for file in files:
					if file.endswith(".gcda"):
						os.remove(os.path.join(root, file))

			# Clean-up and create the coverage directory
			coverageDir = os.path.join(self.config["root"], self.config["buildDir"], "coverage")
			lib.shell(["rm", "-rfd", coverageDir], cwd=self.config["root"])
			lib.shell(["mkdir", coverageDir], cwd=self.config["root"])

			# Reset the coverage counters
			lib.shell(["lcov", "--directory", "'%s'" % (buildDir), "--zerocounters", "-q"], cwd=self.config["root"])

			# Execute an empty run to setup the base
			lib.shell(["lcov", "--capture", "--initial", "--directory", "%s" % (buildDir),
					"--output-file", os.path.join(coverageDir, "lcov_base.info"), "-q"], cwd=self.config["root"])

			#exit(0)

	def runPost(self, *args):

		buildType = self.getDefaultBuildType()
		if self.hasCoverage(buildType):

			coverageDir = os.path.join(self.config["root"], self.config["buildDir"], "coverage")
			buildDir = os.path.join(self.config["root"], self.config["buildDir"], buildType)

			# Execute the run on the previosu executable
			lib.shell(["lcov", "--capture", "--directory", "%s" % (buildDir),
					"--output-file", os.path.join(coverageDir, "lcov_run.info"), "-q"], cwd=self.config["root"])

			# Join info files
			lib.shell(["lcov", "--add-tracefile", os.path.join(coverageDir, "lcov_base.info"), "--add-tracefile", os.path.join(coverageDir, "lcov_run.info"),
					"--output-file", os.path.join(coverageDir, "lcov_full.info"), "-q"], cwd=self.config["root"])

			# Remove external dependencies
			removeCommandList = ["lcov", "--remove", os.path.join(coverageDir, "lcov_full.info"), "-o", os.path.join(coverageDir, "lcov_full.info"), "-q", "/usr/*"]
			for ignore in self.config["staticAnalyzerIgnore"]:
				removeCommandList.append("*/%s/*" % (ignore))
			lib.shell(removeCommandList, cwd=self.config["root"])

			# Generate the report
			outputList = lib.shell(["genhtml", "-o", coverageDir, "-t", "Coverage for '%s' built with configuration '%s'" % (str(args[0]), buildType),
					"--sort", os.path.join(coverageDir, "lcov_full.info")], cwd=self.config["root"], captureStdout=True)

			while outputList:
				line = outputList.pop()
				match = re.search(r'\s*([^\s\.]+)[^\d]*([\d.]+)%', line)
				if not match:
					break
				lib.info("Coverage for '%s': %s%%" % (match.group(1), match.group(2)))

			lib.info("Coverage report generated at '%s'" % (os.path.join(coverageDir, "index.html")))