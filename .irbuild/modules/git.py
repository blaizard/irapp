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
						lib.shell(root, ["git", "init"])

						# Update the index with submodules
						submodulesPath = lib.shell(root, ["git", "config", "-f", ".gitmodules", "--get-regexp", "^submodule\..*\.path$"], captureStdout=True)
						for pathKeyAndPath in submodulesPath:
							pathKeyAndPath = pathKeyAndPath.split(" ", 1)
							urlKey = pathKeyAndPath[0].replace(".path", ".url", 1)
							path = pathKeyAndPath[1]
							url = lib.shell(root, ["git", "config", "-f", ".gitmodules", "--get", urlKey], captureStdout=True)

							lib.info("Add submodule %s to path %s" % (url[0], path))
							lib.shell(root, ["git", "submodule", "add", "-f", url[0], path], ignoreError=True)

		# Update and init the submodules if needed
		if hasGitmodules:
			lib.info("Updating git submodules")
			lib.shell(self.config["root"], ["git", "submodule", "update", "--init", "--recursive"])
