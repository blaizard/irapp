#!/usr/bin/env groovy

pipeline {

	agent none

	stages
	{
		%if staticAnalyzer%
		stage('Check')
		{
			agent
			{
				dockerfile
				{
					filename '%dockerfilePath%'
				}
			}
			steps
			{
				echo "cppcheck Version: ${sh(returnStdout: true, script: 'cppcheck --version')}"
				sh './app.py update'
				sh './app.py init'
				sh 'cppcheck %for ignore in staticAnalyzerIgnore% -i%ignore% --suppress="*:*%ignore%*" %end% --enable=warning,style,performance,portability,unusedFunction,missingInclude --report-progress --inline-suppr --xml --xml-version=2 . 2>cppcheck.xml'
				publishCppcheck(pattern: 'cppcheck.xml', displayAllErrors: true, severityError: true, severityWarning: true, severityStyle: true, severityPortability: true, severityPerformance: true)
			}
		}
		%end%

		stage('Build & Test')
		{
			parallel
			{
				%for buildName, options in buildConfigs%
				stage('%buildName%')
				{
					agent
					{
						dockerfile
						{
							filename '%dockerfilePath%'
						}
					}
					stages
					{
						stage('Build %buildName%')
						{
							steps
							{
								sh './app.py update'
								sh './app.py init'
								sh './app.py build %buildName%'
								%if options.compiler == "clang"% warnings(consoleParsers: [[parserName: 'Clang (LLVM based)']]) %end%
								%if options.compiler == "gcc"% warnings(consoleParsers: [[parserName: 'GNU Make + GNU C Compiler (gcc)']]) %end%
							}
						}
						%if options.tests%
						stage('Tests %buildName%')
						{
							steps
							{
							%for index, test in tests%
								%if options.valgrind%
									sh "valgrind --leak-check=full --show-leak-kinds=all --track-origins=yes --verbose --gen-suppressions=all --suppressions=%valgrindSuppPath% --xml=yes --xml-file=%buildName%_tests_%index%_valgrind.xml %test% --gtest_output=xml:%buildName%_tests_%index%_junit.xml"
								%end%
								%if not options.valgrind%
									sh "%test% --gtest_output=xml:%buildName%_tests_%index%_junit.xml"
								%end%
							%end%
							}
						}
						%end%
					}
					%if options.tests%
					post
					{
						always
						{
							junit '*_junit.xml'
							%if options.valgrind%
								publishValgrind(pattern: '*_valgrind.xml', failThresholdInvalidReadWrite: '0', failThresholdDefinitelyLost: '0', failThresholdTotal: '0', unstableThresholdInvalidReadWrite: '0', unstableThresholdDefinitelyLost: '0', unstableThresholdTotal: '0', sourceSubstitutionPaths: '0', publishResultsForAbortedBuilds: true, publishResultsForFailedBuilds: true, failBuildOnMissingReports: true, failBuildOnInvalidReports: true)
							%end%
						}
					}
					%end%
				}
				%end%
			}
		}
	}
}
