#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .modules import cmake
from .modules import python
from .modules import git
from .modules import default
from .modules import jenkins
from .modules import daemon

def loadModules():
	return {
		"cmake": cmake.CMake,
		"python": python.Python,
		"git": git.Git,
		"default": default.Default,
		"jenkins": jenkins.Jenkins,
		"daemon": daemon.Daemon
	}

def getTypeList():
	return ["git", "default", "cmake", "python", "jenkins", "daemon"]
