# Copyright (c) 2017 Red Hat, Inc. All rights reserved. This copyrighted
# material is made available to anyone wishing to use, modify, copy, or
# redistribute it subject to the terms and conditions of the GNU General
# Public License v.2 or later.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.

import json
import logging
import time

import jenkinsapi

import sktm.misc


class JenkinsProject(object):
    """Jenkins project interface"""
    def __init__(self, name, url, username=None, password=None):
        """
        Initialize a Jenkins project interface.

        Args:
            name:        Name of the Jenkins project to operate on.
            url:         Jenkins instance URL.
            username:    Jenkins user name.
            password:    Jenkins user password.
        """
        self.name = name
        # Initialize Jenkins server interface
        # TODO Add support for CSRF protection
        self.server = jenkinsapi.jenkins.Jenkins(url, username, password)

    def __wait_and_get_build(self, buildid):
        job = self.server.get_job(self.name)
        build = job.get_build(buildid)
        build.block_until_complete(delay=60)

        # call get_build again to ensure we have the results
        build = job.get_build(buildid)

        return build

    def __get_cfg_data(self, buildid, stepname, cfgkey, default=None):
        """
        Get a value from a JSON-formatted output of a test result, of the
        specified completed build. Wait for the build to complete, if it
        hasn't yet.

        Args:
            buildid:    Jenkins build ID.
            stepname:   Test (step) path in the result, which output should be
                        parsed as JSON.
            cfgkey:     Name of the JSON key to retrieve value of.
            default:    The default value to use if the key is not found.
                        Optional, assumed None, if not specified.

        Returns:
            The key value, or the default if not found.
        """
        build = self.__wait_and_get_build(buildid)

        if not build.has_resultset():
            raise Exception("No results for build %d (%s)" %
                            (buildid, build.get_status()))

        for (key, val) in build.get_resultset().iteritems():
            if key == stepname:
                logging.debug("stdout=%s", val.stdout)
                cfg = json.loads(val.stdout)
                return cfg.get(cfgkey, default)

    def get_base_commitdate(self, buildid):
        """
        Get base commit's committer date of the specified completed build.
        Wait for the build to complete, if it hasn't yet.

        Args:
            buildid:    Jenkins build ID.

        Return:
            The epoch timestamp string of the committer date.
        """
        return self.__get_cfg_data(buildid, "skt.cmd_merge", "commitdate")

    def get_base_hash(self, buildid):
        """
        Get base commit's hash of the specified completed build.
        Wait for the build to complete, if it hasn't yet.

        Args:
            buildid:    Jenkins build ID.

        Return:
            The base commit's hash string.
        """
        return self.__get_cfg_data(buildid, "skt.cmd_merge", "basehead")

    def get_patch_url_list(self, buildid):
        """
        Get the list of Patchwork patch URLs for the specified completed
        build. Wait for the build to complete, if it hasn't yet.

        Args:
            buildid:    Jenkins build ID.

        Return:
            The list of Patchwork patch URLs.
        """
        return self.__get_cfg_data(buildid, "skt.cmd_merge", "pw")

    def __get_baseretcode(self, buildid):
        return self.__get_cfg_data(buildid, "skt.cmd_run", "baseretcode", 0)

    def get_result_url(self, buildid):
        """
        Get the URL of the web representation of the specified build.

        Args:
            buildid:    Jenkins build ID.

        Result:
            The URL of the build result.
        """
        return "%s/job/%s/%s" % (self.server.base_server_url(), self.name,
                                 buildid)

    def get_result(self, buildid):
        """
        Get result code (sktm.misc.tresult) for the specified build.
        Wait for the build to complete, if it hasn't yet.

        Args:
            buildid:    Jenkins build ID.

        Result:
            The build result code (sktm.misc.tresult).
        """
        build = self.__wait_and_get_build(buildid)

        bstatus = build.get_status()
        logging.info("build_status=%s", bstatus)

        if bstatus == "SUCCESS":
            return sktm.misc.tresult.SUCCESS

        if not build.has_resultset():
            raise Exception("No results for build %d (%s)" %
                            (buildid, build.get_status()))

        if bstatus == "UNSTABLE" and \
                (build.get_resultset()["skt.cmd_run"].status in
                 ["PASSED", "FIXED"]):
            if self.__get_baseretcode(buildid) != 0:
                logging.warning("baseline failure found during patch testing")
                return sktm.misc.tresult.BASELINE_FAILURE

            return sktm.misc.tresult.SUCCESS

        for (key, val) in build.get_resultset().iteritems():
            if not key.startswith("skt."):
                logging.debug("skipping key=%s; value=%s", key, val.status)
                continue
            logging.debug("key=%s; value=%s", key, val.status)
            if val.status == "FAILED" or val.status == "REGRESSION":
                if key == "skt.cmd_merge":
                    return sktm.misc.tresult.MERGE_FAILURE
                elif key == "skt.cmd_build":
                    return sktm.misc.tresult.BUILD_FAILURE
                elif key == "skt.cmd_run":
                    return sktm.misc.tresult.TEST_FAILURE

        logging.warning("Unknown status. marking as test failure")
        return sktm.misc.tresult.TEST_FAILURE

    # FIXME Clarify/fix argument names
    def build(self, baserepo=None, ref=None, baseconfig=None,
              message_id=None, subject=None, emails=set(), patch_url_list=[],
              makeopts=None):
        """
        Submit a build of a patchset.

        Args:
            baserepo:       Baseline Git repo URL.
            ref:            Baseline Git reference to test.
            baseconfig:     Kernel configuration URL.
            message_id:     Value of the "Message-Id" header of the e-mail
                            message representing the patchset, or None if
                            unknown.
            subject:        Subject of the message representing the patchset,
                            or None if unknown.
            emails:         Set of e-mail addresses involved with the patchset
                            to send notifications to.
            patch_url_list: List of URLs pointing to patches to apply.
            makeopts:       String of extra arguments to pass to the build's
                            make invocation.

        Returns:
            Submitted build number.
        """
        params = dict()
        if baserepo is not None:
            params["baserepo"] = baserepo

        if ref is not None:
            params["ref"] = ref

        if baseconfig is not None:
            params["baseconfig"] = baseconfig

        if message_id:
            params["message_id"] = message_id

        if subject:
            params["subject"] = subject

        if emails:
            params["emails"] = ",".join(emails)

        if patch_url_list:
            params["patchwork"] = " ".join(patch_url_list)

        if makeopts is not None:
            params["makeopts"] = makeopts

        logging.debug(params)
        self.server.get_job(self.name)
        expected_id = self.server.get_job(self.name).get_next_build_number()
        self.server.build_job(self.name, params)
        build = self.__find_build(params, expected_id)
        logging.info("submitted build: %s", build)
        return build.get_number()

    def is_build_complete(self, buildid):
        job = self.server.get_job(self.name)
        build = job.get_build(buildid)

        return not build.is_running()

    def __params_eq(self, build, params):
        try:
            build_params = build.get_actions()["parameters"]
        except (AttributeError, KeyError):
            return False

        for build_param in build_params:
            if (build_param["name"] in params
                    and build_param["value"] != params[build_param["name"]]):
                return False

        return True

    def __find_build(self, params, eid=None):
        job = self.server.get_job(self.name)
        lbuild = None

        while not lbuild:
            try:
                lbuild = job.get_last_build()
            except jenkinsapi.custom_exceptions.NoBuildData:
                time.sleep(1)

        if eid is not None:
            while lbuild.get_number() < eid:
                time.sleep(1)
                lbuild = job.get_last_build()
        if self.__params_eq(lbuild, params):
            return lbuild

        # slowpath
        for bid in job.get_build_ids():
            build = job.get_build(bid)
            if self.__params_eq(build, params):
                return build
        return None
