#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os

class Git(lib.Module):

	@staticmethod
	def config():
		return {
			# Ignore specific configuration from the patterns listed below
			"gitignore.ignore": []
		}

	@staticmethod
	def check(config):
		return os.path.isdir(os.path.join(config["root"], ".git"))

	def init(self):

		# ---- Update gitmodules ----------------------------------------------

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
						submodulesPath = lib.shell(["git", "config", "-f", ".gitmodules", "--get-regexp", "^submodule\..*\.path$"], cwd=root, captureStdout=True)
						for pathKeyAndPath in submodulesPath:
							pathKeyAndPath = pathKeyAndPath.split(" ", 1)
							urlKey = pathKeyAndPath[0].replace(".path", ".url", 1)
							path = pathKeyAndPath[1]
							url = lib.shell(["git", "config", "-f", ".gitmodules", "--get", urlKey], cwd=root, captureStdout=True)

							lib.info("Add submodule %s to path %s" % (url[0], path))
							lib.shell(["git", "submodule", "add", "-f", url[0], path], cwd=root, ignoreError=True)

		# Update and init the submodules if needed
		if hasGitmodules:
			lib.info("Updating git submodules")
			lib.shell(["git", "submodule", "update", "--init", "--recursive"], cwd=self.config["root"])

		# ---- Update .gitignore ----------------------------------------------

		lib.info("Updating .gitignore")

		gitIgnoreStr = ""
		gitIgnorePath = os.path.join(self.config["root"], ".gitignore")
		if os.path.isfile(gitIgnorePath):
			with open(os.path.join(self.config["root"], ".gitignore"),  "r") as f:
				gitIgnoreStr = f.read()
		gitIgnoreList = [line.strip() for line in gitIgnoreStr.split("\n")]

		# Patterns for the various supported types
		patterns = {
			"Irapp": {
				"types": ["git"],
				"patternList": [".irapp/*", "!.irapp/assets/"]
			},
			"Git": {
				"types": ["git"],
				"patternList": ["~*", "*.orig"]
			},
			"Python": {
				"types": ["python"],
				"patternList": [".pyc", "__pycache__/"]
			},
			"C++": {
				"types": ["cmake"],
				"patternList": ["Makefile", "Makefile.old", "*.o", "*.d", "*.so", "*.a", "*.out", "*.gcda", "*.gcno", ".lcovrc"]
			}
		}
		# Delete previous insertions by irapp
		for index, line in enumerate(gitIgnoreList):
			if line.find("Automatically generated content by irapp") != -1:
				gitIgnoreList = gitIgnoreList[:index]
				break
		for name, config in patterns.items():
			if set(config["types"]).intersection(self.config["types"]) and name not in self.config["gitignore.ignore"]:
				gitIgnoreList[:] = [line for line in gitIgnoreList if line not in config["patternList"]]
		gitIgnoreList = "\n".join(gitIgnoreList).rstrip().split("\n")

		gitIgnoreList += ([""] if len(gitIgnoreList) and gitIgnoreList[-1] else []) + [
				"# ---- Automatically generated content by irapp -------------------------------",
				"# Note: everything below this line will be updated"]

		# Add new entries
		for name, config in patterns.items():
			if set(config["types"]).intersection(self.config["types"]) and name not in self.config["gitignore.ignore"]:
				gitIgnoreList += ([""] if len(gitIgnoreList) and gitIgnoreList[-1] else []) + ["# %s" % (name)] + config["patternList"]

		# Write .gitignore
		with open(os.path.join(self.config["root"], ".gitignore"),  "w") as f:
			f.write("\n".join(gitIgnoreList))
