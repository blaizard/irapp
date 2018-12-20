#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os

class Jenkins(lib.Module):

	@staticmethod
	def check(config):
		return True

	@staticmethod
	def config():
		return {
			"staticAnalyzer": True,
			"staticAnalyzerIgnore": [],
			"dependencies": [],
			"tests": []
		}

	"""
	Helper function to modify and publish the Dockerfile
	"""
	def loadAndPublishDockerfile(self, fileName, dependencies):
		# Create the dockerfile image
		with open(self.getAssetPath("dockerfile", fileName), "r") as f:
			dockerfileStr = f.read()

		dockerfileTemplate = lib.Template(dockerfileStr)
		dockerfileStr = dockerfileTemplate.process({
			"dependencies": dependencies
		})
		return self.publishAsset(dockerfileStr, fileName)

	"""
	Helper function to modify and publish the Jenkinsfile
	"""
	def loadAndPublishJenkinsfile(self, fileName, config):
		# Create the Jenkinsfile
		with open(self.getAssetPath("jenkinsfile", fileName), "r") as f:
			jenkinsfileStr = f.read()

		jenkinsfileTemplate = lib.Template(jenkinsfileStr)
		jenkinsfileStr = jenkinsfileTemplate.process(config)

		# Save the Jenkins file
		return self.publishAssetTo(jenkinsfileStr, self.config["root"], "Jenkinsfile")

	"""
	Initialization for C++ projects
	"""
	def initCpp(self):
		# Create the dockerfile image
		dockerfilePath = self.loadAndPublishDockerfile("c++.linux.dockerfile", self.config["dependencies"])

		# Copy the valgrind supp file
		valgrindSuppPath = self.copyAsset("valgrind.supp")

		# Update the buildConfigs with defautl values
		updatedBuildConfigs = {}
		for name, options in self.config["buildConfigs"].items():
			updatedBuildConfigs[name] = {
				"valgrind": False,
				"tests": False,
				"coverage": False
			}
			if options["default"]:
				updatedBuildConfigs[name]["valgrind"] = True
			if options["coverage"]:
				updatedBuildConfigs[name]["coverage"] = True
			if not options["lint"]:
				updatedBuildConfigs[name]["tests"] = True
			updatedBuildConfigs[name].update(options)

		# Create the Jenkinsfile
		self.loadAndPublishJenkinsfile("c++.Jenkinsfile", {
			"dockerfilePath": dockerfilePath,
			"staticAnalyzer": self.config["staticAnalyzer"],
			"staticAnalyzerIgnore": self.config["staticAnalyzerIgnore"],
			"buildConfigs": updatedBuildConfigs,
			"tests": self.config["tests"],
			"valgrindSuppPath": valgrindSuppPath,
			"coverageDir": os.path.join(self.config["buildDir"], "coverage")
		})

	"""
	Initialization for Python projects
	"""
	def initPython(self):
		config = {
			"configs": {
				"Linux": {
					"dockerfilePath": self.loadAndPublishDockerfile("python.linux.dockerfile", self.config["dependencies"]),
					"pythonList": ["python2.7", "python3"]
				}
			},
			"tests": self.config["tests"]
		}
		self.loadAndPublishJenkinsfile("python.Jenkinsfile", config)


	def init(self):
		if "cmake" in self.config["types"]:
			self.initCpp()
		elif "python" in self.config["types"]:
			self.initPython()
