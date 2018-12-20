#!/usr/bin/env groovy
pipeline {
	agent none
	stages
	{
		stage('Test')
		{
			parallel
			{
				stage('Linux')
				{
					agent
					{
						dockerfile
						{
							filename 'assets/python.linux.dockerfile'
						}
					}
					stages
					{
						stage('Tests python2.7')
						{
							steps
							{
								sh "python2.7 --version"
									sh "python2.7 ./tests/unit/testShell.py"
									sh "python2.7 ./tests/endtoend/testCMake.py"
							}
						}
						stage('Tests python3')
						{
							steps
							{
								sh "python3 --version"
									sh "python3 ./tests/unit/testShell.py"
									sh "python3 ./tests/endtoend/testCMake.py"
							}
						}
					}
				}
			}
		}
	}
}