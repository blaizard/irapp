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
			"buildDir": "build",
			"buildConfigs": {
				"gcc-debug": {
					"type": "Debug",
					"compiler": "gcc",
					"default": True
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
			"buildGenerator": generator
		}

	def setDefaultBuild(self, buildType):
		currentBuildTypePath = os.path.join(self.config["root"], self.config["buildDir"], ".buildtype")

		lib.info("Setting '%s' as default build configuration" % (buildType))
		with open(currentBuildTypePath, "w") as f:
			f.write(buildType)

	def init(self):

		# Print cmake version
		cmakeVersion = lib.shell(["cmake", "--version"], captureStdout=True)
		lib.info("CMake version: %s" % (cmakeVersion[0].lower().replace("cmake", "").replace("version", "").strip()))

		# Removing CMake build directory
		buildDirPath = os.path.join(self.config["root"], self.config["buildDir"])
		lib.info("Cleanup CMake build directory at '%s'" % (buildDirPath))
		lib.shell(["rm", "-rfd", os.path.basename(self.config["buildDir"])], cwd=os.path.dirname(buildDirPath))
		lib.shell(["mkdir", os.path.basename(self.config["buildDir"])], cwd=os.path.dirname(buildDirPath))

		# Remove all CMakeCache.txt if existing
		for root, dirs, files in os.walk(self.config["root"]):
			for file in files:
				if file == "CMakeCache.txt":
					os.remove(os.path.join(root, file))

		# Initialize CMake configurations
		defaultBuildType = None
		firstValidBuild = None
		updatedBuildConfigs = {}
		for name, buildConfig in self.config["buildConfigs"].items():

			# Set default values
			updatedBuildConfig = {
				"type": "Debug",
				"compiler": "gcc",
				"default": False
			}
			updatedBuildConfig.update(buildConfig)

			lib.info("Initializing build configuration '%s' with generator '%s'" % (name, str(self.config["buildGenerator"])))
			lib.shell(["mkdir", "-p", name], cwd=buildDirPath)
			buildTypePath = os.path.join(buildDirPath, name)

			# Identify the compiler and ensure it is present
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

			lib.shell(["cmake", "-G", self.config["buildGenerator"], "-DCMAKE_BUILD_TYPE=%s" % (updatedBuildConfig["type"]),
					"-DCMAKE_C_COMPILER=%s" % (cCompiler), "-DCMAKE_CXX_COMPILER=%s" % (cxxCompiler), "../.."], cwd=buildTypePath)

			# Set the default build if any is set
			if updatedBuildConfig["default"]:
				self.setDefaultBuild(name)
				defaultBuildType = name

			# Save the first valid build to identify if any build has been processed
			if not firstValidBuild:
				firstValidBuild = name

			# Update the build config
			updatedBuildConfigs[name] = updatedBuildConfig

		# Set the new build config
		self.config["buildConfigs"] = updatedBuildConfigs

		if not firstValidBuild:
			lib.error("No build configuration has been set.")
			sys.exit(1)
		# Set the defautl build if none explicitly defined
		elif not defaultBuildType:
			self.setDefaultBuild(firstValidBuild)
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
		currentBuildTypePath = os.path.join(buildDirPath, ".buildtype")

		# Read the current configuration if any
		currentBuildType = None
		if os.path.isfile(currentBuildTypePath):
			with open(currentBuildTypePath, "r") as f:
				currentBuildType = f.read()

		# Identifying the defautl buidl type if not explicitly set
		if buildType == None:
			if currentBuildType == None:
				for name in self.config["buildConfigs"]:
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

		lib.shell(["cmake", "--build", os.path.join(buildDirPath, buildType), "--", "-j3"], cwd=self.config["root"])
