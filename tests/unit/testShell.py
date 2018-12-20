#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import base
import unittest

class TestShell(base.UnitTests):

	def testSimple(self):
		output = self.lib.shell(["echo", "hello"], captureStdout=True)
		self.assertEqual(output[0], "hello")

	def testSimpleError(self):
		self.assertRaises(OSError, self.lib.shell, (["notarecognizedcommand"]))
		self.assertRaises(Exception, self.lib.shell, (["ssh", "-tt", "dfsfjisdfhjdsjofhohfdsfsdjfhdsfjkh"]))
		output = self.lib.shell(["ssh", "-tt", "dfsfjisdfhjdsjofhohfdsfsdjfhdsfjkh"], captureStdout=True, ignoreError=True)
		self.assertIn("dfsfjisdfhjdsjofhohfdsfsdjfhdsfjkh", output[0])

	def testMulti(self):
		self.lib.shellMulti([["echo", "hello"], ["echo", "world"]])

	def testMultiError(self):
		self.assertRaises(Exception, self.lib.shellMulti, ([["dfsfjisdfhjdsjofhohfdsfsdjfhdsfjkh", "hello"], ["echo", "world"]]))

if __name__ == '__main__':
	base.UnitTests.main()
