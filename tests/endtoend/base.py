#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

import unittest
import imp
import os
import tempfile
import shutil
import re
import sys
import subprocess

rootDirectory = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
presetDirectory = os.path.normpath(os.path.join(os.path.dirname(__file__), "presets"))

class EndToEndTests(unittest.TestCase):

	def __init__(self, *args):
		self.modules, self.types, self.lib =  EndToEndTests.loadDependencies()
		unittest.TestCase.__init__(self, *args)

	def setUp(self):
		# Create a temporary directory
		self.testDirPath = tempfile.mkdtemp()
		# Include the app.py
		shutil.copyfile(os.path.join(rootDirectory, "app.py"), os.path.join(self.testDirPath, "app.py"))
		# Modify the git repository path
		with open(os.path.join(self.testDirPath, "app.py"), "r") as f:
			content = f.read()
		content = re.sub(r'GIT_REPOSITORY\s*=\s*[^\s]+', "GIT_REPOSITORY = '%s'" % (rootDirectory), content)
		with open(os.path.join(self.testDirPath, "app.py"), "w") as f:
			f.write(content)
		# Update the file
		self.assertIn("succeed", self.app("update"))

	def usePreset(self, name):
		# Use a specific preset
		path = os.path.join(presetDirectory, name)
		self.assertTrue(os.path.isdir(path))
		# Copy the content of the directory
		for fileName in os.listdir(path):
			src = os.path.join(path, fileName)
			dst = os.path.join(self.testDirPath, fileName)
			if os.path.isdir(src):
				shutil.copytree(src, dst)
			else:
				shutil.copyfile(src, dst)

	def tearDown(self):
		# Remove the directory after the test
		shutil.rmtree(self.testDirPath)

	"""
	Execute commands on the app and return the output
	"""
	def app(self, *args):
		process = subprocess.Popen([sys.executable, "./app.py"] + list(args), cwd=self.testDirPath, stdin=None, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
		stdout, stderr = process.communicate()

		output = stdout.decode("utf-8", "ignore")
		if process.returncode != 0:
			print(output)
			raise Exception("Failure: retcode=%s" % (str(process.returncode)))
		return output

	def assertRegex(self, string, regex):
		return re.search(regex, string)

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
