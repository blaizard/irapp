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
	Initialization for C++ projects
	"""
	def initCpp(self):

		# Create the dockerfile image
		with open(self.getAssetPath("jenkins.debian.latest.dockerfile"), "r") as f:
			dockerfileStr = f.read()

		dockerfileTemplate = lib.Template(dockerfileStr)
		dockerfileStr = dockerfileTemplate.process({
			"dependencies": self.config["dependencies"]
		})
		dockerfilePath = self.publishAsset(dockerfileStr, "jenkins.debian.latest.dockerfile")

		# Copy the valgrind supp file
		valgrindSuppPath = self.copyAsset("valgrind.supp")

		# Create the Jenkinsfile
		with open(self.getAssetPath("c++.Jenkinsfile"), "r") as f:
			jenkinsfileStr = f.read()

		# Update the buildConfigs with defautl values
		updatedBuildConfigs = {}
		for name, options in self.config["buildConfigs"].items():
			updatedBuildConfigs[name] = {
				"valgrind": False,
				"tests": True
			}
			if options["default"]:
				updatedBuildConfigs[name]["valgrind"] = True
			updatedBuildConfigs[name].update(options)

		jenkinsfileTemplate = lib.Template(jenkinsfileStr)
		jenkinsfileStr = jenkinsfileTemplate.process({
			"dockerfilePath": dockerfilePath,
			"staticAnalyzer": self.config["staticAnalyzer"],
			"staticAnalyzerIgnore": self.config["staticAnalyzerIgnore"],
			"buildConfigs": updatedBuildConfigs,
			"tests": self.config["tests"],
			"valgrindSuppPath": valgrindSuppPath
		})

		# Save the Jenkins file
		with open(os.path.join(self.config["root"], "Jenkinsfile"), "w") as f:
			f.write(jenkinsfileStr)

	def init(self):
		if "cmake" in self.config["types"]:
			self.initCpp()
