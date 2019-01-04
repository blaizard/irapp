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
			"dependencies": {
				"debian": ["valgrind"]
			},
			"tests": {},
			"templates": {
				"debian": {
					"run": "./%path%"
				}
			}
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

	def init(self):

		# Generate the configs
		builds = {}
		for moduleId, module in self.config["pimpl"].items():
			for buildName, options in module.getConfig(["builds"], noneValue={}, onlySpecific=True).items():
				builds["%s:%s" % (moduleId, buildName)] = dict(options, configs={moduleId: buildName})
		builds = builds or {"": {}}

		# Copy the valgrind suppression file
		valgrindSuppPath = self.copyAsset("valgrind.supp")

		# Generate the various dockerfiles
		configs = {}
		for platform, deps in self.config["dependencies"].items():
			# Remove duplicates and sort the list to ensure the order stays the same after each builds
			deps = list(set(deps))
			deps.sort()
			configs[platform] = {
				"dockerfilePath": self.loadAndPublishDockerfile("%s.dockerfile" % (platform), deps),
				"builds": {}
			}
			# Set default values to build
			for buildName, options in builds.items():
				updatedOptions = {
					"compiler": "unknown",
					"memleaks": False,
					"lint": False,
					"junit": False,
					"tests": [],
					"configs": {},
					# Links to be added
					"links": {},
					# Specific options
					"valgrindSuppPath": valgrindSuppPath
				}
				updatedOptions.update(options)

				# Update the links
				for key, value in updatedOptions["links"].items():
					linkPath = lib.Template(value).process(self.config)
					temp, extension = os.path.splitext(linkPath)
					fileType = {".html": "html", ".htm": "html"}
					updatedOptions["links"][key] = {
						"path": linkPath,
						"dirname": os.path.dirname(linkPath),
						"basename": os.path.basename(linkPath),
						"type": fileType[extension.lower()] if extension.lower() in fileType else "unknown"
					}

				if not updatedOptions["lint"]:
					# Set temporarly the build configurations
					for moduleId, buildConfig in updatedOptions["configs"].items():
						self.config["pimpl"][moduleId].setDefaultBuildType(buildConfig, save=False)

					# Update the tests
					for typeIds, testList in self.config["tests"].items():
						for path in testList:
							for name in ["junit", "test", "run"]:
								execTest = lib.getCommand(self.config, name, "%s.%s" % (platform, typeIds), {
										"report": "%s.%s_%i_%s.report" % (platform, buildName.replace(":", "."), lib.uniqueId(), name),
										"path": path})
								if execTest:
									if name == "junit":
										updatedOptions["junit"] = True
									updatedOptions["tests"].append(execTest)
									break

				configs[platform]["builds"][buildName] = updatedOptions

		self.loadAndPublishJenkinsfile("Jenkinsfile", {"configs": configs})
