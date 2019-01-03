#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib

class Python(lib.Module):
	@staticmethod
	def config():
		return {
			"builds": {
				"v2.7": {
					"executable": "python2.7",
					"default": True
				},
				"v3": {
					"executable": "python3"
				}
			}
		}

	def getCommandsTemplate(self):
		buildType = self.getDefaultBuildType()
		return {
			"run": self.getConfig(["builds", buildType, "executable"], "python") + " %path%"
		}

	"""
	Return the dependencies for the various supported platforms
	"""
	def dependencies(self):
		return {
			"debian": ["python2.7", "python3"]
		}
