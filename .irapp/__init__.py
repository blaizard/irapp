#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .modules import cmake
from .modules import git
from .modules import default
from .modules import jenkins
from .modules import deploy

def loadModules():
	return {
		"cmake": cmake.CMake,
		"git": git.Git,
		"default": default.Default,
		"jenkins": jenkins.Jenkins,
		"deploy": deploy.Deploy
	}

def getTypeList():
	return ["git", "default", "cmake", "jenkins", "deploy"]
