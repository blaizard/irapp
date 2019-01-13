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

	def init(self):
		for file, defaultFile in self.getConfig(["files"]).items():
			if not os.path.isfile(os.path.join(self.config["root"], file)):
				lib.info("Copying default file %s to %s" % (defaultFile, file))
				shutil.copy(os.path.join(self.config["root"], defaultFile), os.path.join(self.config["root"], file))
