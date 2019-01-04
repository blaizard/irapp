#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import base
import unittest

class TestShell(base.EndToEndTests):

	def testSimple(self):
		self.usePreset("cmake")
		initOutput = self.app("init")
		self.assertIn("[INFO]", initOutput)
		self.assertNotIn("[ERROR]", initOutput)
		self.assertRegex(initOutput, r'CMake version: [0-9\.]+')

		buildOutput = self.app("build")
		print(buildOutput)

if __name__ == '__main__':
	base.EndToEndTests.main()
