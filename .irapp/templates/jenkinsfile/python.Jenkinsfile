#!/usr/bin/env groovy

pipeline {

	agent none

	stages
	{
		stage('Test')
		{
			parallel
			{
				%for platform, config in configs%
				stage('%platform%')
				{
					agent
					{
						dockerfile
						{
							filename '%config.dockerfilePath%'
						}
					}
					stages
					{
						%for python in config.pythonList%
						stage('Tests %python%')
						{
							steps
							{
								sh "%python% --version"
								%for test in tests%
									sh "%python% %test%"
								%end%
							}
						}
						%end%
					}
				}
				%end%
			}
		}
	}
}
