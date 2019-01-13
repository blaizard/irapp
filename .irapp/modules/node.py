#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import re
import json

class Node(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isfile(os.path.join(config["root"], "package.json"))

	@staticmethod
	def config():
		return {
			"builds": {
				"eslint": {
					"compiler": "eslint",
					"default": True,
					"lint": True
				}
			}
		}

	"""
	Read the package.json configuration object
	"""
	def readPackageJson(self):
		f = open(os.path.join(self.config["root"], "package.json"), "r")
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
			with open('package.json', 'w') as f:
				json.dump(packageJson, f, indent=4)

	def initLint(self):
		# Add eslint if not present
		self.addDependency("eslint", isDev=True)

		lib.info("Generating '.eslintrc.js'")
		with open(self.getAssetPath(".eslintrc.js"), "r") as f:
			eslintrcStr = f.read()
		eslintrcStr = lib.Template(eslintrcStr).process({})
		with open(os.path.join(self.config["root"], ".eslintrc.js"), "w") as f:
			f.write(eslintrcStr)

		lib.info("Generating '.eslintignore'")
		with open(self.getAssetPath(".eslintignore"), "r") as f:
			eslintignoreStr = f.read()
		eslintignoreStr = lib.Template(eslintignoreStr).process({})
		with open(os.path.join(self.config["root"], ".eslintignore"), "w") as f:
			f.write(eslintignoreStr)

	def init(self):

		# Print npm version
		npmVersion = lib.shell(["npm", "--version"], capture=True)
		lib.info("NPM version: %s" % (lib.getVersion(npmVersion)))

		# Print node version
		nodeVersion = lib.shell(["node", "--version"], capture=True)
		lib.info("Node.js version: %s" % (lib.getVersion(nodeVersion)))

		# Initialize lint
		self.initLint()

		nodeModulesPath = os.path.join(self.config["root"], "node_modules")
		if os.path.isdir(nodeModulesPath):
			lib.info("Removing '%s'" % (nodeModulesPath))
			lib.rmtree(nodeModulesPath)
		lib.info("Importing dependencies...")
		lib.shell(["npm", "install"], cwd=self.config["root"])

	def build(self, target):

		buildType = self.getDefaultBuildType()

		if buildType == "eslint":
			lib.shell(["node", os.path.join("node_modules", "eslint", "bin", "eslint.js"), "."], cwd=self.config["root"], ignoreError=True)
