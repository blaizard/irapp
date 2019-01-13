#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os

class Jenkins(lib.Module):
	@staticmethod
	def config():
		return {
			"staticAnalyzer": True,
			"staticAnalyzerIgnore": [],
			"dependencies": {
				"debian": ["valgrind"]
			},
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
	def loadAndPublishJenkinsfile(self, config):
		# Create the Jenkinsfile
		with open(self.getAssetPath("Jenkinsfile"), "r") as f:
			jenkinsfileStr = f.read()

		jenkinsfileTemplate = lib.Template(jenkinsfileStr)
		jenkinsfileStr = jenkinsfileTemplate.process(config)

		# Save the Jenkins file
		return self.publishAssetTo(jenkinsfileStr, self.config["root"], "Jenkinsfile")

	def init(self):

		# Generate the configs
		builds = {}
		for moduleId, module in self.config["pimpl"].items():
			for buildName, options in module.getConfig(["builds"], default={}, onlySpecific=True).items():
				builds["%s.%s" % (moduleId, buildName)] = dict(options, configs={moduleId: buildName})
		builds = builds or {"": {}}

		# Generate the dependencies
		dependencies = self.config["dependencies"]
		for moduleId, module in self.config["pimpl"].items():
			dependencies = lib.deepMerge(dependencies, module.getConfig(["dependencies"], default={}, onlySpecific=True))

		# Copy the valgrind suppression file
		valgrindSuppPath = self.copyAsset("valgrind.supp")

		# Generate the various dockerfiles
		configs = {}
		for platform, deps in dependencies.items():
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
										"report": "%s.%s_%i_%s.report" % (platform, buildName, lib.uniqueId(), name),
										"path": path})
								if execTest:
									if name == "junit":
										updatedOptions["junit"] = True
									updatedOptions["tests"].append(execTest)
									break

				configs[platform]["builds"][buildName] = updatedOptions

		self.loadAndPublishJenkinsfile({
			"configs": configs,
			"irapp-update": not self.isIgnore("irapp", "update")
		})
