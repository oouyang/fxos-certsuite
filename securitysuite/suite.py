# -*- encoding: utf-8 -*-

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import sys
import logging
import argparse
import traceback
from mozdevice import DeviceManagerADB, DMError, ADBError
from mozlog.structured import commandline, get_default_logger
from time import sleep

from webapi_tests.semiauto.devicehelper import DeviceHelper

# ######################################################################################################################
# Test class that all test must be derived from
###############################################

class ExtraTest(object):
    """
    Parent class for all tests in this suite.
    Every child must set its .group string and implement
    its .run() method.
    """

    @classmethod
    def groupname(cls):
        """
        Getter that returns a test's group name.
        """
        if cls.group:
            return cls.group
        else:
            return 'unknown'

    @staticmethod
    def group_list(mode='phone'):
        """
        Returns a list of all groups in the test suite.
        """
        if mode == 'stingray':
            return ['ssl']
        groups = []
        for t in ExtraTest.__subclasses__():
            if t.groupname() not in groups:
                groups.append(t.groupname())
        return groups

    @staticmethod
    def test_list(group=None, mode='phone'):
        """
        Returns a list of all tests, optionally filtered by group.
        """
        if mode == 'stingray' and group is not None:
            return 'ssl'
        if group is None:
            return ExtraTest.__subclasses__()
        else:
            tests = []
            for t in ExtraTest.__subclasses__():
                if t.groupname() == group:
                    tests.append(t)
            return tests

    @staticmethod
    def run_groups(groups=[], version=None, host='localhost', port=2828, mode='phone'):
        hasadb = mode == 'phone'
        logger = get_default_logger()
        if groups is None or len(groups) == 0:  # run all groups
            logger.debug('running securitysuite tests for all groups %s' % str(ExtraTest.group_list(mode=mode)))
            groups = ExtraTest.group_list(mode=mode)
        else:
            logger.debug('running securitysuite tests for groups %s' % str(groups))
        logger.suite_start(tests=groups)
        
        # setup marionette before any test
        marionette = DeviceHelper.getMarionette(host=host, port=port)
        # setup device before any test
        device = DeviceHelper.getDevice(runAdbAsRoot=True)

        for g in groups:
            logger.debug("running securitysuite test group %s" % g)
            logger.test_start(g)
            try:
                ExtraTest.run(g, version=version)
                logger.test_end(g, 'OK')
            except:
                logger.critical(traceback.format_exc())
                logger.test_end(g, 'FAIL')
                raise
        logger.suite_end()

    @classmethod
    def run(cls, group=None, version=None):
        """
        Runs all the tests, optionally just within the specified group.
        """
        for t in cls.test_list(group):
            t.run(version=version)

    @classmethod
    def log_status(cls, status, msg):
        logger = get_default_logger()
        logger.test_status(cls.groupname(), cls.__name__, status, message=msg)


#######################################################################################################################
# Shared module functionality
#############################

def wait_for_adb_device():
    try:
        #adb = DeviceManagerADB()
        adb = DeviceHelper.getDevice()
    except DMError:
        adb = None
        print "Waiting for adb connection..."
    while adb is None:
        try:
            #adb = DeviceManagerADB()
            adb = DeviceHelper.getDevice()
        except DMError:
            sleep(0.2)
    if len(adb.devices()) < 1:
        print "Waiting for adb device..."
        while len(adb.devices()) < 1:
            sleep(0.2)


def adb_has_root():
    # normally this should check via root=True to .shellCheckOutput, but doesn't work
    #adb = DeviceManagerADB()
    adb = DeviceHelper.getDevice()
    return adb.shellCheckOutput(["id"]).startswith("uid=0(root)")


#######################################################################################################################
# Command line handler
######################

def securitycli():
    """
    Entry point for the runner defined in setup.py.
    """

    parser = argparse.ArgumentParser(description="Runner for security test suite")
    parser.add_argument("-l", "--list-test-groups", action="store_true",
                        help="List all logical test groups")
    parser.add_argument("-a", "--list-all-tests", action="store_true",
                        help="List all tests")
    parser.add_argument("-i", "--include", metavar="GROUP", action="append", default=[],
                        help="Only include specified group(s) in run, include several "
                             "groups by repeating flag")
    parser.add_argument("--version", action="store", dest="version",
                        help="B2G version")
    parser.add_argument("--ipython", dest="ipython", action="store_true",
                        help="drop to ipython session")
    parser.add_argument('-H', '--host',
                        help='Hostname or ip for target device',
                        action='store', default='localhost')
    parser.add_argument('-P', '--port',
                        help='Port for target device',
                        action='store', default=2828)
    parser.add_argument('-m', '--mode',
                        help='Test mode (stingray, phone) default (phone)',
                        action='store', default='phone')
    parser.add_argument("-v", dest="verbose", action="store_true",
                        help="Verbose output")

    # add specialized mozilla logger options
    commandline.add_logging_group(parser)
    args = parser.parse_args()

    # set up mozilla logger
    logger = commandline.setup_logging("securitysuite", vars(args), {"raw": sys.stdout})

    try:
        logger.debug("security cli runnng with args %s" % args)
        if args.list_test_groups:
            for group in ExtraTest.group_list(args.mode):
                print group
        elif args.list_all_tests:
            for test in ExtraTest.test_list(args.mode):
                print "%s.%s" % (test.group, test.__name__)
        elif args.ipython:
            from IPython import embed

            embed()
        elif args.mode == 'stingray':
            ExtraTest.run_groups(args.include,
                                 version=args.version,
                                 host=args.host, port=int(args.port),
                                 mode=args.mode)
        else:
            wait_for_adb_device()
            if not adb_has_root():
                logger.warning("adb has no root. Results will be incomplete.")
            ExtraTest.run_groups(args.include, version=args.version)

    except:
        logger.critical(traceback.format_exc())
        raise


if __name__ == "__main__":
    securitycli()

