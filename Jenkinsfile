#!/usr/bin/env groovy
/**
 * It requires the following Jenkins plugins to work:
 * - Warnings Next Generation
 * - JUnit Plugin
 * - valgrind
 */
pipeline {
	agent none
	stages
	{
		stage('Platforms')
		{
			parallel
			{
						stage('debian.python:v3')
						{
							agent
							{
								dockerfile
								{
									filename 'assets/debian.dockerfile'
								}
							}
							stages
							{
								stage('Build debian.python:v3')
								{
									steps
									{
										sh './app.py update'
										sh './app.py init'
										sh './app.py build  -c python:v3 '
									}
								}
									stage('Test debian.python:v3')
									{
										steps
										{
												sh "./app.py run  --cmd 'python3 tests/unit/testShell.py'  --cmd 'python3 tests/endtoend/testCMake.py'  -j0"
										}
									}
							}
							post
							{
								always
								{
									// Publish the warnings from the various compiler or static analyzers
									// Publish junit test reports
								}
							}
						}
						stage('debian.python:v2.7')
						{
							agent
							{
								dockerfile
								{
									filename 'assets/debian.dockerfile'
								}
							}
							stages
							{
								stage('Build debian.python:v2.7')
								{
									steps
									{
										sh './app.py update'
										sh './app.py init'
										sh './app.py build  -c python:v2.7 '
									}
								}
									stage('Test debian.python:v2.7')
									{
										steps
										{
												sh "./app.py run  --cmd 'python2.7 tests/unit/testShell.py'  --cmd 'python2.7 tests/endtoend/testCMake.py'  -j0"
										}
									}
							}
							post
							{
								always
								{
									// Publish the warnings from the various compiler or static analyzers
									// Publish junit test reports
								}
							}
						}
			}
		}
	}
}