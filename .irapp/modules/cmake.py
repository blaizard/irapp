#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import re
import json

class CMake(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isfile(lib.path(config["root"], "CMakeLists.txt"))

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
			"binDir": "build/bin",
			"libDir": "build/lib",
			"buildGenerator": "Ninja" if lib.which("ninja") else "Unix Makefiles",
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
						"Coverage Report": "%cmake.buildDir%/coverage/index.html"
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
					"lint": "clang-tidy"
				},
				"cppcheck": {
					"compiler": "cppcheck",
					"lint": "cppcheck"
				}
			}
		}

	@staticmethod
	def configDescriptor():
		return {
			"buildDir": {
				"type": [str],
				"example": ".irapp/build",
				"help": "Path of the directory that will contain the build metadata."
			},
			"binDir": {
				"type": [str],
				"example": ".irapp/build/bin",
				"help": "Path of the directory that will receive the binaries."
			},
			"libDir": {
				"type": [str],
				"example": ".irapp/build/lib",
				"help": "Path of the directory that will receive the libraries."
			},
			"buildGenerator": {
				"type": [str],
				"example": "Unix Makefiles",
				"help": "Build generator to be used for this project."
			}
		}

	def hasCoverage(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.getConfig(["builds", buildType, "coverage"], default=False)

	def hasLint(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.getConfig(["builds", buildType, "lint"], default=False)

	def getType(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()
		# Check if this is a coverage build
		return self.getConfig(["builds", buildType, "type"], default="Debug")

	def getCompiler(self, buildType=None):
		if not buildType:
			buildType = self.getDefaultBuildType()

		# Check if this is a coverage build
		return self.getConfig(["builds", buildType, "compiler"], default="gcc")

	def init(self):

		# Print cmake version
		cmakeVersion = lib.shell(["cmake", "--version"], capture=True)
		lib.info("CMake version: %s" % (lib.getVersion(cmakeVersion)))

		# Removing CMake build directory
		buildDirPath = lib.path(self.config["root"], self.getConfig(["buildDir"]))
		lib.info("Cleanup CMake build directory at '%s'" % (buildDirPath))
		# Try to cleanup the build directory, not critical if it fails
		lib.shell(["rm", "-rfd", os.path.basename(buildDirPath)], cwd=os.path.dirname(buildDirPath), ignoreError=True)
		lib.shell(["mkdir", os.path.basename(buildDirPath)], cwd=os.path.dirname(buildDirPath), ignoreError=True)

		# Remove all CMakeCache.txt if existing
		for root, dirs, files in os.walk(self.config["root"]):
			for file in files:
				if file == "CMakeCache.txt":
					os.remove(lib.path(root, file))

		# Initialize CMake configurations
		defaultBuildType = None
		firstValidBuild = None
		for name, buildConfig in self.getConfig(["builds"]).items():

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

			# Set the command
			commandList = ["cmake", "-G", self.getConfig(["buildGenerator"]), "-DCMAKE_BUILD_TYPE=%s" % (updatedBuildConfig["type"]),
					"-DCMAKE_ARCHIVE_OUTPUT_DIRECTORY=%s" % (lib.path(self.config["root"], self.getConfig(["libDir"]))),
					"-DCMAKE_LIBRARY_OUTPUT_DIRECTORY=%s" % (lib.path(self.config["root"], self.getConfig(["libDir"]))),
					"-DCMAKE_RUNTIME_OUTPUT_DIRECTORY=%s" % (lib.path(self.config["root"], self.getConfig(["binDir"])))]

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

			lib.info("Initializing build configuration '%s' with generator '%s'" % (name, str(self.getConfig(["buildGenerator"]))))
			lib.shell(["mkdir", "-p", name], cwd=buildDirPath)
			buildTypePath = lib.path(buildDirPath, name)

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

	def clean(self):

		buildDirPath = lib.path(self.config["root"], self.getConfig(["buildDir"]))
		lib.info("Cleaning %s" % (buildDirPath))
		lib.shell(["rm", "-rfd", lib.path(buildDirPath, "bin")], cwd=self.config["root"])
		lib.shell(["rm", "-rfd", lib.path(buildDirPath, "lib")], cwd=self.config["root"])
		lib.shell(["mkdir", lib.path(buildDirPath, "bin")], cwd=self.config["root"])
		lib.shell(["mkdir", lib.path(buildDirPath, "lib")], cwd=self.config["root"])

	def build(self, target=None):

		buildDirPath = lib.path(self.config["root"], self.getConfig(["buildDir"]))

		# Identifying the build type if not explicitly set
		buildType = self.getDefaultBuildType()

		lib.info("Building configuration: %s" % (buildType))

		if self.hasLint(buildType):

			# Read the compile_commands.json file
			compileCommandsJson = lib.path(self.config["root"], self.getConfig(["buildDir"]), buildType, "compile_commands.json")
			try:
				with open(compileCommandsJson, "r") as f:
					compileCommandListRaw = json.load(f)
			except Exception as e:
				lib.fatal("Could not open '%s': %s" % (compileCommandsJson, str(e)))

			# Filter some entries and generate the command
			compileCommandList = []
			for command in compileCommandListRaw:
				ignore = False
				for ignoreStr in self.getConfig(["lintIgnore"]):
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
			if compiler == "clang-tidy":
				# Print clang-tidy version
				clangTidyVersion = lib.shell(["clang-tidy", "--version"], capture=True)
				lib.info("clang-tidy version: %s" % (lib.getVersion(clangTidyVersion)))
				for command in compileCommandList:
					# Do not use "-quiet" as it is not recognized in earlier versions of clang-tidy
					commandList.append(["clang-tidy", "-p", command["directory"], command["file"]])

			elif compiler == "cppcheck":
				# Print clang-tidy version
				cppcheckVersion = lib.shell(["cppcheck", "--version"], capture=True)
				lib.info("cppcheck version: %s" % (lib.getVersion(cppcheckVersion)))
				ignoreArgList = []
				for ignoreStr in self.getConfig(["lintIgnore"]):
					ignoreArgList += ["-i", ignoreStr, "--suppress=*:*%s*" % (ignoreStr)]
				for command in compileCommandList:
					commandList.append(["cppcheck", "--enable=warning,style,performance,portability,unusedFunction,missingInclude", "--inline-suppr"]
							+ ignoreArgList
							+ ["-I%s" % (include) for include in command["include"]]
							+ [command["file"]])
				options["hideStdout"] = True

			else:
				lib.failure("Unsupported compiler '%s' for lint" % (compiler))

			# Run everything
			lib.shellMulti(commandList,
					cwd=".",
					verbose=True,
					verboseCommand=True,
					nbJobs=self.getConfig(["parallelism"]),
					hideStdout=options["hideStdout"],
					hideStderr=options["hideStderr"],
					ignoreError=True)
		else:
			lib.shell(["cmake", "--build", lib.path(buildDirPath, buildType), "--target", target if target else "all", "--", "-j%i" % (self.getConfig(["parallelism"]))],
					cwd=self.config["root"])

	def info(self, verbose):

		defaultBuildType = self.getDefaultBuildType()
		buildDir = lib.path(self.config["root"], self.getConfig(["buildDir"]))
		info = {
			"buildGenerator": self.getConfig(["buildGenerator"]),
			"builds": {}
		}

		# List all build types and their properties
		for buildType, buildConfig in self.getConfig(["builds"]).items():
			# Check if available
			buildPath = lib.path(buildDir, buildType)
			buildPath = buildPath if os.path.isdir(buildPath) else None
			if buildPath:
				info["builds"][buildType] = {
					"default": (defaultBuildType == buildType),
					"type": self.getType(buildType),
					"compiler": self.getCompiler(buildType),
					"coverage": self.hasCoverage(buildType),
					"lint": self.hasLint(buildType),
					"path": buildPath
				}

		if verbose:
			lib.info("Using build generator '%s'" % (self.getConfig(["buildGenerator"])))

		# List the default targets
		buildDirPath = lib.path(self.config["root"], self.getConfig(["buildDir"]))

		# Ignore the errors, it means that init command was not run
		try:
			targetsRaw = lib.shell(["cmake", "--build", lib.path(buildDirPath, defaultBuildType), "--target", "help"], cwd=self.config["root"], capture=True)
			info["targets"] = [re.search("\.+\s+([^\s]+)", targetStr).group(1) for targetStr in targetsRaw[1:] if re.search("\.+\s+([^\s]+)", targetStr)]
		except:
			pass

		return info

	def runPre(self, commandList):

		buildType = self.getDefaultBuildType()
		if self.hasCoverage(buildType):

			lib.info("Preparing coverage run")
			lcovVersion = lib.shell(["lcov", "--version"], capture=True)
			lib.info("lcov version: %s" % (lib.getVersion(lcovVersion)))
			gcovVersion = lib.shell(["gcov", "--version"], capture=True)
			lib.info("gcov version: %s" % (lib.getVersion(gcovVersion)))

			# Clean-up directory by removing all previous gcda files
			buildDir = lib.path(self.config["root"], self.getConfig(["buildDir"]), buildType)
			for root, dirs, files in os.walk(buildDir):
				for file in files:
					if file.endswith(".gcda"):
						os.remove(lib.path(root, file))

			# Clean-up and create the coverage directory
			coverageDir = lib.path(self.config["root"], self.getConfig(["buildDir"]), "coverage")
			lib.shell(["rm", "-rfd", coverageDir], cwd=self.config["root"])
			lib.shell(["mkdir", coverageDir], cwd=self.config["root"])

			# Reset the coverage counters
			lib.shell(["lcov", "--directory", "'%s'" % (buildDir), "--zerocounters", "-q"], cwd=self.config["root"])

			# Execute an empty run to setup the base
			lib.shell(["lcov", "--capture", "--initial", "--directory", "%s" % (buildDir),
					"--output-file", lib.path(coverageDir, "lcov_base.info"), "-q"], cwd=self.config["root"])

	def runPost(self, commandList):

		buildType = self.getDefaultBuildType()
		if self.hasCoverage(buildType):

			coverageDir = lib.path(self.config["root"], self.getConfig(["buildDir"]), "coverage")
			buildDir = lib.path(self.config["root"], self.getConfig(["buildDir"]), buildType)

			# Execute the run on the previosu executable
			lib.shell(["lcov", "--capture", "--directory", "%s" % (buildDir),
					"--output-file", lib.path(coverageDir, "lcov_run.info"), "-q"], cwd=self.config["root"])

			# Join info files
			lib.shell(["lcov", "--add-tracefile", lib.path(coverageDir, "lcov_base.info"), "--add-tracefile", lib.path(coverageDir, "lcov_run.info"),
					"--output-file", lib.path(coverageDir, "lcov_full.info"), "-q"], cwd=self.config["root"])

			# Remove external dependencies
			removeCommandList = ["lcov", "--remove", lib.path(coverageDir, "lcov_full.info"), "-o", lib.path(coverageDir, "lcov_full.info"), "-q", "/usr/*"]
			for ignore in self.getConfig(["lintIgnore"]):
				removeCommandList.append("*/%s/*" % (ignore))
			lib.shell(removeCommandList, cwd=self.config["root"])

			# Generate the report
			outputList = lib.shell(["genhtml", "-o", coverageDir, "-t", "Coverage for %s built with configuration '%s'" % (", ".join([("'" + str(command[0]) + "'") for command in commandList]), buildType),
					"--sort", lib.path(coverageDir, "lcov_full.info")], cwd=self.config["root"], capture=True)

			while outputList:
				line = outputList.pop()
				match = re.search(r'\s*([^\s\.]+)[^\d]*([\d.]+)%', line)
				if not match:
					break
				lib.info("Coverage for '%s': %s%%" % (match.group(1), match.group(2)))

			lib.info("Coverage report generated at '%s'" % (lib.path(coverageDir, "index.html")))
