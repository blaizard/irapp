#!/usr/bin/python
# -*- coding: iso-8859-1 -*-

from .modules import cmake
from .modules import python
from .modules import git
from .modules import default
from .modules import jenkins
from .modules import daemon
from .modules import node

# Modules sorted by order
moduleList = [git.Git, default.Default, cmake.CMake, node.Node, python.Python, jenkins.Jenkins, daemon.Daemon]

def loadModules():
	return {module.name(): module for module in moduleList}

def getTypeList():
	return [module.name() for module in moduleList]
