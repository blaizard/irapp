#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import re
import json

class CMake(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isfile(os.path.join(config["root"], "CMakeLists.txt"))

	@staticmethod
	def config():
		return {
			"dependencies": {
				"debian": ["cmake", "ninja-build", "cppcheck", "g++", "clang", "clang-tidy", "lcov"]
			},
			"templates": {
				"gtest": {
					"junit": "%run% --gtest_output=xml:%report%"
				}
			},
			"buildDir": "build",
			"builds": {
				"gcc-debug": {
					"type": "Debug",
					"compiler": "gcc",
					"memleaks": True,
					"default": True
				},
				"gcc-coverage": {
					"type": "Debug",
					"compiler": "gcc",
					"coverage": True,
					"links": {
						"Coverage Report": "%buildDir%/coverage/index.html"
					}
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
				},
				"clang-tidy": {
					"type": "Debug",
					"compiler": "clang-tidy",
					"lint": True
				},
				"cppcheck": {
					"compiler": "cppcheck",
					"lint": True
				}
			},
			"buildGenerator": "Ninja" if lib.which("ninja") else "Unix Makefiles",
			"staticAnalyzerIgnore": [],
		}

	def hasCoverage(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return ("coverage" in self.config["builds"][buildType]) and (self.config["builds"][buildType]["coverage"])

	def hasLint(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return ("lint" in self.config["builds"][buildType]) and (self.config["builds"][buildType]["lint"])

	def getType(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.config["builds"][buildType]["type"] if ("type" in self.config["builds"][buildType]) else "Debug"

	def getCompiler(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.config["builds"][buildType]["compiler"] if ("compiler" in self.config["builds"][buildType]) else "gcc"

	def init(self):

		# Print cmake version
		cmakeVersion = lib.shell(["cmake", "--version"], capture=True)
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
		for name, buildConfig in self.config["builds"].items():

			# Set default values and update the build config
			updatedBuildConfig = {
				"type": self.getType(name),
				"compiler": self.getCompiler(name),
				"coverage": self.hasCoverage(name),
				"lint": self.hasLint(name),
				"default": False,
				"available": False
			}
			updatedBuildConfig.update(buildConfig)
			self.config["builds"][name] = updatedBuildConfig

			# Set the command
			commandList = ["cmake", "-G", self.config["buildGenerator"], "-DCMAKE_BUILD_TYPE=%s" % (updatedBuildConfig["type"])]

			# ---- Compiler specific options ----------------------------------

			# Identify the compiler and ensure it is present
			isCoverageError = False
			isLintError = False

			# ---- GCC
			if updatedBuildConfig["compiler"] == "gcc":
				cCompiler = lib.which("gcc")
				cxxCompiler = lib.which("g++")
				if updatedBuildConfig["coverage"]:
					if lib.which("lcov"):
						self.copyAssetTo(".", ".lcovrc")
						commandList.extend(["-DCMAKE_CXX_FLAGS=--coverage", "-DCMAKE_C_FLAGS=--coverage"])
						lib.info("Adding compilation flag '--coverage'")
					else:
						isCoverageError = True
				if updatedBuildConfig["lint"]:
					isLintError = True

			# ---- CLANG
			elif updatedBuildConfig["compiler"] in ["clang", "clang-tidy"]:
				cCompiler = lib.which("clang")
				cxxCompiler = lib.which("clang++")
				if updatedBuildConfig["coverage"]:
					isCoverageError = True
				if updatedBuildConfig["lint"]:
					if lib.which("clang-tidy"):
						commandList.extend(["-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"])
					else:
						isLintError = True

			# ---- CPPCHECK
			elif updatedBuildConfig["compiler"] == "cppcheck":
				if lib.which("cppcheck"):
					commandList.extend(["-DCMAKE_EXPORT_COMPILE_COMMANDS=ON"])
				else:
					isLintError = True

			else:
				lib.fatal("Unkown compiler '%s' for build configuration '%s'" % (str(updatedBuildConfig["compiler"]), name))

			if isCoverageError:
				lib.warning("Unable to find coverage tools for '%s', ignoring configuration '%s'" % (updatedBuildConfig["compiler"], name))
				continue

			if isLintError:
				lib.warning("Unable to find lint tools for '%s', ignoring configuration '%s'" % (updatedBuildConfig["compiler"], name))
				continue

			if not updatedBuildConfig["lint"]:
				if not cCompiler or not cxxCompiler:
					lib.warning("Unable to find compiler for '%s', ignoring configuration '%s'" % (updatedBuildConfig["compiler"], name))
					continue

				# Add the compilers
				commandList.extend(["-DCMAKE_C_COMPILER=%s" % (cCompiler), "-DCMAKE_CXX_COMPILER=%s" % (cxxCompiler)])

			# -----------------------------------------------------------------

			# Mark the configuration as available if it is for this platform
			self.config["builds"][name]["available"] = True

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
			lib.fatal("No build configuration has been set.")
		# Set the defautl build if none explicitly defined
		elif not defaultBuildType:
			self.setDefaultBuildType(firstValidBuild)
			self.config["builds"][firstValidBuild]["default"] = True

	def clean(self):

		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])
		lib.info("Cleaning %s" % (buildDirPath))
		lib.shell(["rm", "-rfd", os.path.join(buildDirPath, "bin")], cwd=self.config["root"])
		lib.shell(["rm", "-rfd", os.path.join(buildDirPath, "lib")], cwd=self.config["root"])
		lib.shell(["mkdir", os.path.join(buildDirPath, "bin")], cwd=self.config["root"])
		lib.shell(["mkdir", os.path.join(buildDirPath, "lib")], cwd=self.config["root"])

	def build(self, target=None):

		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])

		# Identifying the build type if not explicitly set
		buildType = self.getDefaultBuildType()

		lib.info("Building configuration: %s" % (buildType))

		if self.hasLint(buildType):

			# Read the compile_commands.json file
			compileCommandsJson = os.path.join(self.config["root"], self.config["buildDir"], buildType, "compile_commands.json")
			try:
				with open(compileCommandsJson, "r") as f:
					compileCommandListRaw = json.load(f)
			except Exception as e:
				lib.fatal("Could not open '%s': %s" % (compileCommandsJson, str(e)))

			# Filter some entries and generate the command
			compileCommandList = []
			for command in compileCommandListRaw:
				ignore = False
				for ignoreStr in self.config["staticAnalyzerIgnore"]:
					if command["file"].find(ignoreStr) != -1:
						ignore = True
						break
				if not ignore:
					command["include"] = []
					for includePathArg in ["-I", "--sysroot", "-isysroot"]:
						nextIsIncludePath = False
						for arg in command["command"].split():
							if arg == includePathArg:
								nextIsIncludePath = True
							elif arg.find(includePathArg) == 0:
								command["include"].append(arg[2:])
							elif nextIsIncludePath:
								command["include"].append(arg)
								nextIsIncludePath = False
					compileCommandList.append(command)

			# Specific options that can be overriten
			options = {
				"hideStdout": False,
				"hideStderr": False
			}

			commandList = []
			compiler = self.getCompiler(buildType)
			if compiler == "clang":
				# Print clang-tidy version
				clangTidyVersion = lib.shell(["clang-tidy", "--version"], capture=True)
				lib.info("clang-tidy version: %s" % (re.search(r'([\d.]+)', clangTidyVersion[1]).group(1)))
				for command in compileCommandList:
					commandList.append(["clang-tidy", "-p", command["directory"], "-quiet", command["file"]])

			elif compiler == "cppcheck":
				# Print clang-tidy version
				cppcheckVersion = lib.shell(["cppcheck", "--version"], capture=True)
				lib.info("cppcheck version: %s" % (re.search(r'([\d.]+)', cppcheckVersion[0]).group(1)))
				ignoreArgList = []
				for ignoreStr in self.config["staticAnalyzerIgnore"]:
					ignoreArgList += ["-i", ignoreStr, "--suppress=*:*%s*" % (ignoreStr)]
				for command in compileCommandList:
					commandList.append(["cppcheck", "--enable=warning,style,performance,portability,unusedFunction,missingInclude", "--inline-suppr"]
							+ ignoreArgList
							+ ["-I%s" % (include) for include in command["include"]]
							+ [command["file"]])
				options["hideStdout"] = True

			# Run everything
			lib.shellMulti(commandList,
					cwd=".",
					verbose=True,
					verboseCommand=True,
					nbJobs=self.config["parallelism"],
					hideStdout=options["hideStdout"],
					hideStderr=options["hideStderr"],
					ignoreError=True)
		else:
			lib.shell(["cmake", "--build", os.path.join(buildDirPath, buildType), "--target", target if target else "all", "--", "-j%i" % (self.config["parallelism"])],
					cwd=self.config["root"])

	def info(self, verbose):

		defaultBuildType = self.getDefaultBuildType()
		buildDir = os.path.join(self.config["root"], self.config["buildDir"])
		info = {
			"buildGenerator": self.config["buildGenerator"],
			"configList": []
		}

		# List all build types and their properties
		for buildType, buildConfig in self.config["builds"].items():
			# Check if available
			buildPath = os.path.join(buildDir, buildType)
			buildPath = buildPath if os.path.isdir(buildPath) else None
			if buildPath:
				info["configList"].append({
					"id": buildType,
					"default": (defaultBuildType == buildType),
					"type": self.getType(buildType),
					"compiler": self.getCompiler(buildType),
					"coverage": self.hasCoverage(buildType),
					"lint": self.hasLint(buildType),
					"path": buildPath
				})
		info["configList"].sort(key=lambda config: config["id"])

		if verbose:
			lib.info("Build configurations (using '%s'):" % (self.config["buildGenerator"]))
			templateStr = "%15s %1s %8s %10s %4s %4s %s"
			lib.info(templateStr % ("Name", "", "Type", "Compiler", "Cov.", "Lint", "Path"))
			for config in info["configList"]:
				lib.info(templateStr % (config["id"], "x" if config["default"] else "", config["type"], config["compiler"], "x" if config["coverage"] else "", "x" if config["lint"] else "", config["path"]))

		# List the default targets
		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])
		targetsRaw = lib.shell(["cmake", "--build", os.path.join(buildDirPath, defaultBuildType), "--target", "help"], cwd=self.config["root"], capture=True)
		info["targetList"] = [re.search("\.+\s+([^\s]+)", targetStr).group(1) for targetStr in targetsRaw[1:] if re.search("\.+\s+([^\s]+)", targetStr)]
		if verbose:
			lib.info("Targets for '%s': %s" % (defaultBuildType, ", ".join(info["targetList"])))

		return info

	def runPre(self, commandList):

		buildType = self.getDefaultBuildType()
		if self.hasCoverage(buildType):

			lib.info("Preparing coverage run")
			lcovVersion = lib.shell(["lcov", "--version"], capture=True)
			lib.info("lcov version: %s" % (re.search(r'([\d.]+)', lcovVersion[0]).group(1)))
			gcovVersion = lib.shell(["gcov", "--version"], capture=True)
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

	def runPost(self, commandList):

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
			outputList = lib.shell(["genhtml", "-o", coverageDir, "-t", "Coverage for %s built with configuration '%s'" % (", ".join([("'" + str(command[0]) + "'") for command in commandList]), buildType),
					"--sort", os.path.join(coverageDir, "lcov_full.info")], cwd=self.config["root"], capture=True)

			while outputList:
				line = outputList.pop()
				match = re.search(r'\s*([^\s\.]+)[^\d]*([\d.]+)%', line)
				if not match:
					break
				lib.info("Coverage for '%s': %s%%" % (match.group(1), match.group(2)))

			lib.info("Coverage report generated at '%s'" % (os.path.join(coverageDir, "index.html")))
