#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os

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
			"cmakeBuildDir": "build",
			"cmakeBuildConfigs": {
				"gcc-debug": {
					"type": "Debug",
					"compiler": "gcc"
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
			"cmakeGenerator": generator
		}

	def setDefaultBuild(self, buildType):
		currentBuildTypePath = os.path.join(self.config["root"], self.config["cmakeBuildDir"], ".buildtype")

		lib.info("Setting '%s' as default build configuration" % (buildType))
		with open(currentBuildTypePath, "w") as f:
			f.write(buildType)

	def init(self):
		# Removing CMake build directory
		buildDirPath = os.path.join(self.config["root"], self.config["cmakeBuildDir"])
		lib.info("Cleanup CMake build directory at '%s'" % (buildDirPath))
		lib.shell(os.path.dirname(buildDirPath), ["rm", "-rfd", os.path.basename(self.config["cmakeBuildDir"])])
		lib.shell(os.path.dirname(buildDirPath), ["mkdir", os.path.basename(self.config["cmakeBuildDir"])])

		# Initialize CMake configurations
		defaultBuildType = None
		for name, buildConfig in self.config["cmakeBuildConfigs"].items():

			# Set default values
			updatedBuildConfig = {
				"type": "Debug",
				"compiler": "gcc"
			}
			updatedBuildConfig.update(buildConfig)

			lib.info("Initializing build configuration '%s' with generator '%s'" % (name, str(self.config["cmakeGenerator"])))
			lib.shell(buildDirPath, ["mkdir", "-p", name])
			buildTypePath = os.path.join(buildDirPath, name)

			if updatedBuildConfig["compiler"] == "gcc":
				cCompiler = lib.which("gcc")
				cxxCompiler = lib.which("g++")
			elif updatedBuildConfig["compiler"] == "clang":
				cCompiler = lib.which("clang")
				cxxCompiler = lib.which("clang++")
			else:
				lib.error("Unkown compiler '%s' for build configuration '%s'" % (str(updatedBuildConfig["compiler"]), name))
				sys.exit(1)

			if not cCompiler or not cxxCompiler:
				lib.warning("Unable to find compiler for '%s', ignoring configuration '%s'" % (updatedBuildConfig["compiler"], name))
				continue

			lib.shell(buildTypePath, ["cmake", "-G", self.config["cmakeGenerator"], "-DCMAKE_BUILD_TYPE=%s" % (updatedBuildConfig["type"]),
					"-DCMAKE_C_COMPILER=%s" % (cCompiler), "-DCMAKE_CXX_COMPILER=%s" % (cxxCompiler), "../.."])

			if not defaultBuildType:
				self.setDefaultBuild(name)
				defaultBuildType = name

		if not defaultBuildType:
			lib.error("No build configuration has been set.")
			sys.exit(1)

	def clean(self):

		buildDirPath = os.path.join(self.config["root"], self.config["cmakeBuildDir"])
		lib.info("Cleaning %s" % (buildDirPath))
		lib.shell(self.config["root"], ["rm", "-rfd", os.path.join(buildDirPath, "bin")])
		lib.shell(self.config["root"], ["rm", "-rfd", os.path.join(buildDirPath, "lib")])
		lib.shell(self.config["root"], ["mkdir", os.path.join(buildDirPath, "bin")])
		lib.shell(self.config["root"], ["mkdir", os.path.join(buildDirPath, "lib")])

	def build(self, buildType = None, *args):

		buildDirPath = os.path.join(self.config["root"], self.config["cmakeBuildDir"])
		currentBuildTypePath = os.path.join(buildDirPath, ".buildtype")

		# Read the current configuration if any
		currentBuildType = None
		if os.path.isfile(currentBuildTypePath):
			with open(currentBuildTypePath, "r") as f:
				currentBuildType = f.read()

		# Identifying the defautl buidl type if not explicitly set
		if buildType == None:
			if currentBuildType == None:
				for name in self.config["cmakeBuildConfigs"]:
					buildType = name
					break
			else:
				buildType = currentBuildType

		buildType = buildType
		lib.info("Building configuration: %s" % (buildType))

		# If the build type is different then clean the directory
		if buildType != currentBuildType:
			self.clean()
			self.setDefaultBuild(buildType)

		lib.shell(self.config["root"], ["cmake", "--build", os.path.join(buildDirPath, buildType), "--", "-j3"])
