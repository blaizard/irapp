#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import unittest
import imp
import os

class UnitTests(unittest.TestCase):

	def __init__(self, *args):
		self.modules, self.types, self.lib =  UnitTests.loadDependencies()
		unittest.TestCase.__init__(self, *args)

	@staticmethod
	def main():
		unittest.main()

	@staticmethod
	def loadDependencies():
		libPath = os.path.normpath(os.path.join(os.path.realpath(os.path.dirname(__file__)), "..", "..", ".irapp"))
		irapp = imp.load_module("irapp", None, libPath, ('', '', imp.PKG_DIRECTORY))
		if not irapp:
			raise Exception("Could not load dependencies")
		return irapp.loadModules(), irapp.getTypeList(), irapp.lib
