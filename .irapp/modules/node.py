#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import re
import json

class Node(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isfile(lib.path(config["root"], "package.json"))

	@staticmethod
	def config():
		return {
			"builds": {
				"eslint-nyc": {
					"default": True,
					"lint": "eslint",
					"coverage": "nyc",
					"executable": Node.getExecutable("nyc") + " --reporter=html --reporter=text --reporter=text-summary",
					"links": {
						"Coverage Report": "coverage/index.html"
					}
				}
			},
			"templates": {
				"mocha": {
					"test":  "%node.build.executable% " + Node.getExecutable("mocha") + " %path%"
				}
			}
		}

	"""
	Build the executable name
	"""
	@staticmethod
	def getExecutable(name):
		return lib.path("node_modules", ".bin", name)

	"""
	Read the package.json configuration object
	"""
	def readPackageJson(self):
		f = open(lib.path(self.config["root"], "package.json"), "r")
		with f:
			return json.load(f)

	"""
	Check if a certain dependency is present in the package.json
	"""
	def isDependency(self, name):
		packageJson = self.readPackageJson()
		if "dependencies" in packageJson:
			if name in packageJson["dependencies"]:
				return True
		if "devDependencies" in packageJson:
			if name in packageJson["devDependencies"]:
				return True
		return False

	"""
	Add a certain dependency if not present in the package.json
	"""
	def addDependency(self, name, version="latest", isDev=False):
		if not self.isDependency(name):
			lib.info("Adding package '%s' to package.json" % (name))
			packageJson = self.readPackageJson()
			dependenciesKey = "devDependencies" if isDev else "dependencies"
			if dependenciesKey not in packageJson:
				packageJson[dependenciesKey] = {}
			packageJson[dependenciesKey][name] = version
			with open(lib.path(self.config["root"], "package.json"), 'w') as f:
				json.dump(packageJson, f, indent=4)

	def initLint(self):
		# Add eslint if not present
		self.addDependency("eslint", isDev=True)

		lib.info("Generating '.eslintrc.js'")
		with open(self.getAssetPath(".eslintrc.js"), "r") as f:
			eslintrcStr = f.read()
		eslintrcStr = lib.Template(eslintrcStr).process({})
		with open(lib.path(self.config["root"], ".eslintrc.js"), "w") as f:
			f.write(eslintrcStr)

		lib.info("Generating '.eslintignore'")
		with open(self.getAssetPath(".eslintignore"), "r") as f:
			eslintignoreStr = f.read()
		eslintignoreStr = lib.Template(eslintignoreStr).process({
			"ignoreList": self.getConfig(["lintIgnore"], [])
		})
		with open(lib.path(self.config["root"], ".eslintignore"), "w") as f:
			f.write(eslintignoreStr)

	def initCoverage(self):
		self.addDependency("nyc", isDev=True)

	def init(self):

		# Print npm version
		npmVersion = lib.shell(["npm", "--version"], capture=True)
		lib.info("NPM version: %s" % (lib.getVersion(npmVersion)))

		# Print node version
		nodeVersion = lib.shell(["node", "--version"], capture=True)
		lib.info("Node.js version: %s" % (lib.getVersion(nodeVersion)))

		# Initialize lint
		self.initLint()

		# Initialize coverage
		self.initCoverage()

		nodeModulesPath = lib.path(self.config["root"], "node_modules")
		if os.path.isdir(nodeModulesPath):
			lib.info("Removing '%s'" % (nodeModulesPath))
			lib.rmtree(nodeModulesPath)
		lib.info("Importing dependencies...")
		lib.shell(["npm", "install"], cwd=self.config["root"])

	def build(self, target):

		buildType = self.getDefaultBuildType()

		if "eslint" in buildType:
			lib.shell([Node.getExecutable("eslint"), "."], cwd=self.config["root"], ignoreError=True)
