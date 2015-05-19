Interpreting results
====================

After running the FxOS Certification Suite, a result file will be generated
(firefox-os-certification_timestamp.zip by default) in the current directory.
Inside this file are several logs; you need to review two of these to
understand the cert suite's results.

**report.html**
----------------

There are 3 sections in **report.html**.

1.  **Device Information** 

    Device information provide by the user in the first time run the MCTS scripts and it's the basic information about the target testing device. 
    

#.  **Test Results**
    
    The test results use a table to give a summary of the MCTS results. The first column gives the subsuite name, the second column gives the running test count information, and the last column provides the detail subsuite test results links and user could click the links to get details information.

   The color of the second column has different meanings.

   * **green** The test is PASS without failure and error
   * **blue** The test result is not fully PASS. Need to check the details sub-suite report to clarify the failures.
   * **red** There is error when running the test. Need to check the details sub-suite to find more information.
    
3.  **Details log information**

    The details log information provide some extra information related to the testing results.
    This information helps engineer to know more details about the test.


**Sub-suite report**
----------------------------------------

The information in the sub-suite report is displayed when you click the details columns in test results table. If there are failures and errors, we can check more information in sub-suite report. There are 2 sections.

1. Errors Table

 This table is optional table. It's only displayed when there is error when running the tests. You can find the hints about how the errors happen.

2. Regressions Table

 This table always display what tests are run. The first and second columns are the names of the test and sub-test. The rest columns provide the expected result and test result. If the test failed or need shows extra information, there is extra row displayed below the related test. 

The results.html file
---------------------

This file contains the results of all PASS/FAIL tests run by the cert suite,
including the webapi tests, the web-platform-tests, and the webIDL tests.

The cert/cert_results.html file
-------------------------------

This file contains informative test output that needs to be interpreted
by a human engineer.  It contains the following sections:

omni_result
'''''''''''
This section contains the output of the omni_analyzer tool.  The omni_alayzer
compares all the JS files in omni.ja on the device against a reference
version.  If any differences are found, they are displayed here.

Differences in omni.ja files are not failures; they are simply changes that
should be reviewed in order to verify that they are harmless, from a
branding perspective.

application_ini
'''''''''''''''
This section contains the details inside the application.ini on the device.
This section is informative.

headers
'''''''
This section contains all of the HTTP headers, including the user-agent
string, that the device transmits when requesting network resources.  This
section is informative.

buildprops
''''''''''
This section contains the full list of Android build properties that
the device reports.  This section is informative.

kernel_version
''''''''''''''
This section contains the kernel version that the device reports.  This
section in informative.

processes_running
'''''''''''''''''
This section contains a list of all the processes that were running on the
device at the time the test was performed.  This section is informative.

[web|privileged|certified]_unexpected_webidl_results
''''''''''''''''''''''''''''''''''''''''''''''''''''
This section, if present, represents differences in how interfaces defined
in WebIDL files in a reference version differ from the interfaces found
on the device in an (unprivileged|privileged|certified) context.
For example:

    {
      "message": "assert_true: The prototype object must have a property \"textTracks\" expected true got false",
      "name": "HTMLMediaElement interface: attribute textTracks",
      "result": "FAIL"
    },

This means that the HTMLMediaElement interface was expected to expose
a textTracks attribute, but that attribute was not found on the device.

[web|privileged|certified]_added_webidl_results
'''''''''''''''''''''''''''''''''''''''''''''''
This section, if present, represents new, unexpected APIs which are
exposed to applications in an (unprivileged|privileged|certified) context
on the test device, but which are not present on a reference device.

[web|privileged|certified]_missing_webidl_results
'''''''''''''''''''''''''''''''''''''''''''''''
This section, if present, represents APIs which are missing
in an (unprivileged|privileged|certified) context on the test device,
but which are present on a reference device.

[web|privileged|certified]_added_window_functions
'''''''''''''''''''''''''''''''''''''''''''''''''
This section, if present, lists objects descended from the top-level 'window'
object which are present on a reference version, but not present on the device,
in an (unprivileged|privileged|certified) context.

[web|privileged|certified]_missing_window_functions
'''''''''''''''''''''''''''''''''''''''''''''''''''
This section, if present, lists objects descended from the top-level 'window'
object which are present on the device, but not on a reference version, in
an (unprivileged|privileged|certified) context.
