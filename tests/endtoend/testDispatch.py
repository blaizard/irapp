#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import base
import unittest
import json

class TestDispatch(base.EndToEndTests):

	def testSimple(self):
		self.usePreset("dispatch")
		initOutput = self.app("init")
		self.assertIn("[INFO]", initOutput)
		self.assertIn("[1] [INFO]", initOutput)
		self.assertIn("[2] [INFO]", initOutput)
		self.assertNotIn("[ERROR]", initOutput)
		self.assertRegex(initOutput, r'Python version: [0-9\.]+')

		buildOutput = self.app("build")
		print(buildOutput)

		testOutput = self.app("test")
		self.assertIn("Project 1", testOutput)
		self.assertIn("Project 2", testOutput)
		print(testOutput)

		# Test the json output
		testInfo = self.app("info", "--json")
		print(testInfo)
		info = json.loads(testInfo)
		self.assertIn("dispatchResults", info)
		self.assertIn("project1", info["dispatchResults"])
		self.assertIn("project2", info["dispatchResults"])

if __name__ == '__main__':
	base.EndToEndTests.main()
