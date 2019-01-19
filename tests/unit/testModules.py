#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import base
import unittest

class TestModules(base.UnitTests):

	def testSanityCheck(self):
		for moduleId, module in self.modules.items():
			self.lib.configSanityCheck({moduleId: module.config()}, modules={moduleId: module})

if __name__ == '__main__':
	base.UnitTests.main()
