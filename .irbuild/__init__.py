#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .modules import cmake
from .modules import git
from .modules import default

def loadModules():
	return {
		"cmake": cmake.CMake,
		"git": git.Git,
		"default": default.Default
	}

def getTypeList():
	return ["git", "default", "cmake"]
