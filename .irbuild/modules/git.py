#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os

class Git(lib.Module):

	@staticmethod
	def check(config):
		return os.path.isdir(os.path.join(config["root"], ".git"))

	def init(self):
		# Updating gitmodule repos if any
		hasGitmodules = False
		for root, dirs, files in os.walk(self.config["root"]):
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
