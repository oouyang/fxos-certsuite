#!/usr/bin/env python

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this file,
# You can obtain one at http://mozilla.org/MPL/2.0/.

import argparse
import json
import os
import pkg_resources
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
import zipfile

from collections import OrderedDict
from datetime import datetime

import marionette
import mozdevice
import mozprocess

from marionette_extension import AlreadyInstalledException
from marionette_extension import install as marionette_install
from mozfile import TemporaryDirectory
from mozlog.structured import structuredlog, handlers, formatters

from reportmanager import ReportManager
from logmanager import LogManager

import gaiautils
import report


logger = None
stdio_handler = handlers.StreamHandler(sys.stderr,
                                       formatters.MachFormatter())
config_path = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "config.json"))


def setup_logging(log_manager):
    global logger
    log_f = log_manager.structured_file
    logger = structuredlog.StructuredLogger("firefox-os-cert-suite")
    logger.add_handler(stdio_handler)
    logger.add_handler(handlers.StreamHandler(log_f,
                                              formatters.JSONFormatter()))


def load_config(path):
    with open(path) as f:
        config = json.load(f)
    config["suites"] = OrderedDict(config["suites"])
    return config


def iter_test_lists(suites_config):
    '''
    Query each subharness for the list of test groups it can run and
    yield a tuple of (subharness, test group) for each one.
    '''
    for name, opts in suites_config.iteritems():
        try:
            cmd = [opts["cmd"], '--list-test-groups'] + opts.get("common_args", [])
            for group in subprocess.check_output(cmd).splitlines():
                yield name, group
        except (subprocess.CalledProcessError, OSError) as e:
            # There's no logger at this point in the code to log this as an exception
            print >> sys.stderr, "Failed to run command: %s: %s" % (" ".join(cmd), e)
            sys.exit(1)


def get_metadata():
    dist = pkg_resources.get_distribution("fxos-certsuite")
    return {"version": dist.version}


def log_metadata():
    metadata = get_metadata()
    for key in sorted(metadata.keys()):
        logger.info("fxos-certsuite %s: %s" % (key, metadata[key]))

# Consider upstreaming this to marionette-client:
class MarionetteSession(object):
    def __init__(self, adb):
        self.dm = adb
        self.marionette = marionette.Marionette()

    def __enter__(self):
        self.dm.forward("tcp:2828", "tcp:2828")
        self.marionette.wait_for_port()
        self.marionette.start_session()
        return self.marionette

    def __exit__(self, *args, **kwargs):
        if self.marionette.session is not None:
            self.marionette.delete_session()


class Device(object):
    """Represents a device under test.  This class provides encapsulation of
    the things that the harness does when it takes and relinquishes ownership
    of the device."""

    backup_dirs = ["/data/local", "/data/b2g/mozilla"]
    backup_files = ["/system/etc/hosts"]
    test_settings = {"screen.automatic-brightness": False,
                     "screen.brightness": 1.0,
                     "screen.timeout": 0.0,
                     "lockscreen.enabled": False}

    def __init__(self, adb):
        self.adb = adb

    def __enter__(self):
        self.backup()
        logger.info("Setting up device for testing")
        with MarionetteSession(self.adb) as marionette:
            settings = gaiautils.Settings(marionette)
            for k, v in self.test_settings.iteritems():
                settings.set(k, v)
        return self

    def __exit__(self, *args, **kwargs):
        logger.info("Tearing down device after testing")
        # Original settings are reinstated by Device.restore
        shutil.rmtree(self.backup_path)

    def local_dir(self, remote):
        return os.path.join(self.backup_path, remote.lstrip("/"))

    def backup(self):
        logger.info("Backing up device state")
        self.backup_path = tempfile.mkdtemp()

        for remote_path in self.backup_dirs:
            local_path = self.local_dir(remote_path)
            if not os.path.exists(local_path):
                os.makedirs(local_path)
            self.adb.getDirectory(remote_path, local_path)

        for remote_path in self.backup_files:
            remote_dir, filename = remote_path.rsplit("/", 1)
            local_dir = self.local_dir(remote_dir)
            local_path = os.path.join(local_dir, filename)
            if not os.path.exists(local_dir):
                os.makedirs(local_dir)
            self.adb.getFile(remote_path, local_path)

    def restore(self):
        logger.info("Restoring device state")
        self.adb.remount()

        for remote_path in self.backup_files:
            remote_dir, filename = remote_path.rsplit("/", 1)
            local_path = os.path.join(self.local_dir(remote_dir), filename)
            self.adb.removeFile(remote_path)
            self.adb.pushFile(local_path, remote_path)

        for remote_path in self.backup_dirs:
            local_path = self.local_dir(remote_path)
            self.adb.removeDir(remote_path)
            self.adb.pushDir(local_path, remote_path)

    def reboot(self):
        logger.info("Rebooting device")
        self.adb.reboot(wait=True)
        # Bug 1045671: Because the reboot function has a race condition and
        # sometimes returns too soon, we are forced to rely on an arbitrary 30
        # second sleep to be sure we're issuing the next command to the right
        # device.
        time.sleep(30)


class TestRunner(object):
    def __init__(self, args, config):
        self.args = args
        self.config = config

    def iter_suites(self):
        '''
        Iterate over test suites and groups of tests that are to be run. Returns
        tuples of the form (suite, [test_groups]) where suite is the name of a
        test suite and [test_groups] is a list of group names to run in that suite,
        or the empty list to indicate all tests.
        '''
        if not self.args.tests:
            tests = self.config["suites"].keys()
        else:
            tests = self.args.tests

        d = OrderedDict()
        for t in tests:
            v = t.split(":", 1)
            suite = v[0]
            if suite not in d:
                d[suite] = []

            if len(v) == 2:
                #TODO: verify tests passed against possible tests?
                d[suite].append(v[1])

        for suite, groups in d.iteritems():
            yield suite, groups

    def run_suite(self, suite, groups, log_manager, report_manager):
        with TemporaryDirectory() as temp_dir:
            result_files, structured_path = self.run_test(suite, groups, temp_dir)

            for path in result_files:
                file_name = os.path.split(path)[1]
                log_manager.add_file(path, "%s/%s" % (suite, file_name))

            report_manager.add_subsuite_report(structured_path)

    def run_test(self, suite, groups, temp_dir):
        logger.info('Running suite %s' % suite)

        def on_output(line):
            written = False
            if line.startswith("{"):
                try:
                    data = json.loads(line.strip())
                    if "action" in data:
                        sub_logger.log_raw(data)
                        written = True
                except ValueError:
                    pass
            if not written:
                logger.process_output(proc.pid,
                                      line.decode("utf8", "replace"),
                                      command=" ".join(cmd))

        try:
            cmd, output_files, structured_path = self.build_command(suite, groups, temp_dir)

            logger.debug(cmd)
            logger.debug(output_files)

            env = dict(os.environ)
            env['PYTHONUNBUFFERED'] = '1'
            proc = mozprocess.ProcessHandler(cmd, env=env, processOutputLine=on_output)
            logger.debug("Process '%s' is running" % " ".join(cmd))
            #TODO: move timeout handling to here instead of each test?
            with open(structured_path, "w") as structured_log:
                sub_logger = structuredlog.StructuredLogger(suite)
                sub_logger.add_handler(stdio_handler)
                sub_logger.add_handler(handlers.StreamHandler(structured_log,
                                                              formatters.JSONFormatter()))
                proc.run()
                proc.wait()
            logger.debug("Process finished")

        except Exception:
            logger.error("Error running suite %s:\n%s" % (suite, traceback.format_exc()))
            raise
        finally:
            try:
                proc.kill()
            except:
                pass

        return output_files, structured_path

    def build_command(self, suite, groups, temp_dir):
        suite_opts = self.config["suites"][suite]

        subn = self.config.copy()
        del subn["suites"]
        subn.update({"temp_dir": temp_dir})

        cmd = [suite_opts['cmd']]

        log_name = "%s/%s_structured_%s.log" % (temp_dir, suite, "_".join(item.replace("/", "-") for item in groups))
        cmd.extend(["--log-raw=-"])

        if groups:
            cmd.extend('--include=%s' % g for g in groups)

        cmd.extend(item % subn for item in suite_opts.get("run_args", []))
        cmd.extend(item % subn for item in suite_opts.get("common_args", []))

        output_files = [log_name]
        output_files += [item % subn for item in suite_opts.get("extra_files", [])]

        return cmd, output_files, log_name


def log_result(results, result):
    results[result.test_name] = {'status': 'PASS' if result.passed else 'FAIL',
                                 'failures': result.failures,
                                 'errors': result.errors}


def create_adb():
    try:
        logger.info("Testing ADB connection")
        dm = mozdevice.DeviceManagerADB(runAdbAsRoot=True)
        if dm.processInfo("adbd")[2] != "root":
            logger.critical("Your device should allow us to run adb as root.")
            sys.exit(1)
        return mozdevice.DeviceManagerADB()
    except mozdevice.DMError as e:
        logger.critical('Error connecting to device via adb (error: %s). Please be '
                        'sure device is connected and "remote debugging" is enabled.' %
                        e.msg)
        logger.critical(traceback.format_exc())
        raise


def install_marionette(version):
    try:
        logger.info("Installing marionette extension")
        try:
            marionette_install(version)
        except AlreadyInstalledException:
            logger.info("Marionette is already installed")
    except subprocess.CalledProcessError:
        logger.critical(
            "Error installing marionette extension:\n%s" % traceback.format_exc())
        raise


def list_tests(args, config):
    for test, group in iter_test_lists(config["suites"]):
        print "%s:%s" % (test, group)
    return True


def run_tests(args, config):
    error = False
    output_zipfile = None
    runner = TestRunner(args, config)

    try:
        with LogManager() as log_manager, ReportManager() as report_manager:
            output_zipfile = log_manager.zip_path
            setup_logging(log_manager)
            report_manager.setup_report(log_manager.zip_file,
                    log_manager.subsuite_results, log_manager.structured_path)

            log_metadata()
            adb = create_adb()
            install_marionette(config['version'])

            with Device(adb) as device:
                for suite, groups in runner.iter_suites():
                    try:
                        runner.run_suite(suite, groups, log_manager, report_manager)
                    except:
                        logger.error("Encountered error:\n%s" %
                                     traceback.format_exc())
                        error = True
                    finally:
                        device.restore()
                        device.reboot()

            if error:
                logger.critical("Encountered errors during run")
    except (SystemExit, KeyboardInterrupt):
        logger.info("Testrun interrupted")
    except:
        error = True
        print "Encountered error at top level:\n%s" % traceback.format_exc()
    finally:
        if output_zipfile:
            print >> sys.stderr, "Results saved to %s" % output_zipfile

    return error


def get_parser():
    parser = argparse.ArgumentParser()
    #TODO make this more robust
    parser.add_argument('--config',
                        help='Path to config file', type=os.path.abspath,
                        action='store', default=config_path)
    parser.add_argument('--list-tests',
                        help='list all tests available to run',
                        action='store_true')
    parser.add_argument('tests',
                        metavar='TEST',
                        help='tests to run',
                        nargs='*')
    return parser


def main():
    parser = get_parser()
    args = parser.parse_args()
    config = load_config(args.config)

    if args.list_tests:
        return list_tests(args, config)
    else:
        return run_tests(args, config)


if __name__ == '__main__':
    sys.exit(not main())
