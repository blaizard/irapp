#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os

class Git(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isdir(os.path.join(config["root"], ".git"))

	# ---- gitignore rules ----------------------------------------------------

	@staticmethod
	def gitignoreIrapp():
		return [".irapp/*",
				"!.irapp/assets/"]

	@staticmethod
	def gitignoreGit():
		return ["~*",
				"*.orig",
				"*.back"]

	@staticmethod
	def gitignorePython():
		return ["*.pyc",
				"__pycache__/"]

	@staticmethod
	def gitignoreCpp():
		return ["Makefile",
				"Makefile.old",
				"*.o",
				"*.d",
				"*.so",
				"*.a",
				"*.out",
				"*.gcda",
				"*.gcno",
				".lcovrc"]

	@staticmethod
	def gitignoreNode():
		return ["node_modules/",
				".eslintcache"
				".nuxt"]

	# ---- Update Credential Helper -------------------------------------------

	"""
	This will save your password setting for the next X hours or use your machine
	credential store
	"""
	def initCredential(self):

		# Cleanup the credential
		lib.shell(["git", "config", "--local", "--remove-section", "credential"], cwd=self.config["root"], ignoreError=True, hideStdout=True, hideStderr=True)

		if self.config["platform"] == "windows":
			lib.info("Using 'manager' to store Git credentials")
			lib.shell(["git", "config", "--local", "credential.helper", "manager"])
		elif self.config["platform"] == "macos":
			lib.info("Using 'keychain' to store Git credentials")
			lib.shell(["git", "config", "--local", "credential.helper", "osxkeychain"])
		else:
			lib.info("Using cache to store Git credentials (24h)")
			lib.shell(["git", "config", "--local", "credential.helper", "cache --timeout=86400"])

	# ---- Update gitmodules ----------------------------------------------

	def initGitmodule(self):
		# Updating gitmodule repos if any
		hasGitmodules = False
		for root, dirs, files in os.walk(self.config["root"]):
			# Ignore any directories from the following list
			for blackListDir in [".git", "node_modules"]:
				if blackListDir in dirs:
					dirs.remove(blackListDir)

			for file in files:
				if file == ".gitmodules":
					hasGitmodules = True
					gitmodulesPath = os.path.join(root, file)
					gitDirPath = os.path.join(root, ".git")

					# If no git directory is present, create it
					if not os.path.isdir(gitDirPath):
						lib.shell(["git", "init"], cwd=root)

						# Update the index with submodules
						submodulesPath = lib.shell(["git", "config", "-f", ".gitmodules", "--get-regexp", "^submodule\..*\.path$"], cwd=root, capture=True)
						for pathKeyAndPath in submodulesPath:
							pathKeyAndPath = pathKeyAndPath.split(" ", 1)
							urlKey = pathKeyAndPath[0].replace(".path", ".url", 1)
							path = pathKeyAndPath[1]
							url = lib.shell(["git", "config", "-f", ".gitmodules", "--get", urlKey], cwd=root, capture=True)

							lib.info("Add submodule %s to path %s" % (url[0], path))
							lib.shell(["git", "submodule", "add", "-f", url[0], path], cwd=root, ignoreError=True)

		# Update and init the submodules if needed
		if hasGitmodules:
			lib.info("Updating git submodules")
			lib.shell(["git", "submodule", "update", "--init", "--recursive"], cwd=self.config["root"])

	# ---- Update .gitignore ----------------------------------------------

	def initGitignore(self):
		lib.info("Updating .gitignore")

		gitIgnoreStr = ""
		gitIgnorePath = os.path.join(self.config["root"], ".gitignore")
		if os.path.isfile(gitIgnorePath):
			with open(os.path.join(self.config["root"], ".gitignore"),  "r") as f:
				gitIgnoreStr = f.read()
		gitIgnoreList = [line.strip() for line in gitIgnoreStr.split("\n")]

		# Patterns for the various supported types
		patterns = {
			"irapp": {
				"display": "Irapp",
				"types": ["git"],
				"patternList": Git.gitignoreIrapp()
			},
			"git": {
				"display": "Git",
				"types": ["git"],
				"patternList": Git.gitignoreGit()
			},
			"python": {
				"display": "Python",
				"types": ["python"],
				"patternList": Git.gitignorePython()
			},
			"cpp": {
				"display": "C++",
				"types": ["cmake"],
				"patternList": Git.gitignoreCpp()
			},
			"node": {
				"display": "NodeJs",
				"types": ["node"],
				"patternList": Git.gitignoreNode()
			}
		}
		# Delete previous insertions by irapp
		for index, line in enumerate(gitIgnoreList):
			if line.find("Automatically generated content by irapp") != -1:
				gitIgnoreList = gitIgnoreList[:index]
				break

		# Delete redundant entries
		for name, config in patterns.items():
			if set(config["types"]).intersection(self.config["types"]) and not self.isIgnore("gitignore", name):
				gitIgnoreList[:] = [line for line in gitIgnoreList if line not in config["patternList"]]
		gitIgnoreList = "\n".join(gitIgnoreList).rstrip().split("\n")

		gitIgnoreList += ([""] if len(gitIgnoreList) and gitIgnoreList[-1] else []) + [
				"# ---- Automatically generated content by irapp -------------------------------",
				"# Note: everything below this line will be updated"]

		# Add new entries
		for name, config in patterns.items():
			if set(config["types"]).intersection(self.config["types"]) and not self.isIgnore("gitignore", name):
				gitIgnoreList += ([""] if len(gitIgnoreList) and gitIgnoreList[-1] else []) + ["# %s" % (config["display"])] + config["patternList"]

		# Write .gitignore
		with open(os.path.join(self.config["root"], ".gitignore"),  "w") as f:
			f.write("\n".join(gitIgnoreList))


	def init(self):

		self.initGitmodule()
		self.initGitignore()
		self.initCredential()
