#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .. import lib
import os
import shutil

class Default(lib.Module):

	@staticmethod
	def check(config):
		return ("default" in config)

	@staticmethod
	def config():
		return {
			"files": {}
		}

	@staticmethod
	def configDescriptor():
		return {
			"files": {
				"type": [dict, str],
				"example": {"config.hpp": "config.example.hpp"},
				"help": "Copy a default file if it does not exists."
			}
		}

	def init(self):
		for file, defaultFile in self.getConfig(["files"]).items():
			if not os.path.isfile(lib.path(self.config["root"], file)):
				lib.info("Copying default file %s to %s" % (defaultFile, file))
				shutil.copy(lib.path(self.config["root"], defaultFile), lib.path(self.config["root"], file))
