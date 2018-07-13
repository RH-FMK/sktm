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

import logging
import os
import re
import subprocess
import time

import enum

import sktm.db
import sktm.jenkins
import sktm.patchwork


class tresult(enum.IntEnum):
    """Test result"""
    SUCCESS = 0
    MERGE_FAILURE = 1
    BUILD_FAILURE = 2
    PUBLISH_FAILURE = 3
    TEST_FAILURE = 4
    BASELINE_FAILURE = 5


class jtype(enum.IntEnum):
    """Job type"""
    BASELINE = 0
    PATCHWORK = 1


# TODO This is no longer just a watcher. Rename/refactor/describe accordingly.
class watcher(object):
    def __init__(self, jenkinsurl, jenkinslogin, jenkinspassword,
                 jenkinsjobname, dbpath, patch_filter, makeopts=None):
        """
        Initialize a "watcher".

        Args:
            jenkinsurl:         Jenkins instance URL.
            jenkinslogin:       Jenkins user name.
            jenkinspassword:    Jenkins user password.
            jenkinsjobname:     Name of the Jenkins job to trigger and watch.
            dbpath:             Path to the job status database file.
            patch_filter:       The name of a patch series filter program.
                                The program should accept a list of mbox URLs
                                as its arguments, pointing to the patches to
                                apply, and also a "-c/--cover" option,
                                specifying the cover letter mbox URL, if any.
                                The program must exit with zero if the
                                series can be tested, one if it shouldn't be
                                tested at all, and 127 if an error occurred.
                                All other exit codes are reserved.
            makeopts:           Extra arguments to pass to "make" when
                                building.
        """
        # FIXME Clarify/fix member variable names
        # Database instance
        self.db = sktm.db.SktDb(os.path.expanduser(dbpath))
        # Jenkins interface instance
        self.jk = sktm.jenkins.skt_jenkins(jenkinsurl, jenkinslogin,
                                           jenkinspassword)
        # Jenkins project name
        self.jobname = jenkinsjobname
        # Patchset filter program
        self.patch_filter = patch_filter
        # Extra arguments to pass to "make"
        self.makeopts = makeopts
        # List of pending Jenkins builds, each one represented by a 3-tuple
        # containing:
        # * Build type (jtype)
        # * Build number
        # * Patchwork interface to get details of the tested patch from
        self.pj = list()
        # List of Patchwork interfaces
        self.pw = list()
        # True if REST-based Patchwork interfaces should be created,
        # False if XML RPC-based Patchwork interfaces should be created
        self.restapi = False
        # Baseline-related attributes, set by set_baseline() call
        self.baserepo = None
        self.baseref = None
        self.cfgurl = None

    def set_baseline(self, repo, ref="master", cfgurl=None):
        """
        Set baseline parameters.

        Args:
            repo:   Git repository URL.
            ref:    Git reference to test.
            cfgurl: Kernel configuration URL.
        """
        self.baserepo = repo
        self.baseref = ref
        self.cfgurl = cfgurl

    # FIXME The argument should not have a default
    # FIXME This function should likely not exist
    def set_restapi(self, restapi=False):
        """
        Set the type of the next added Patchwork interface.

        Args:
            restapi:    True if the next added interface will be REST-based,
                        false, if it will be XML RPC-based.
        """
        self.restapi = restapi

    def cleanup(self):
        for (pjt, bid, _) in self.pj:
            logging.warning("Quiting before job completion: %d/%d", bid, pjt)

    # FIXME Pass patchwork type via arguments, or pass a whole interface
    def add_pw(self, baseurl, pname, lpatch=None, apikey=None, skip=[]):
        """
        Add a Patchwork interface with specified parameters.
        Add an XML RPC-based interface, if self.restapi is false,
        add a REST-based interface, if self.restapi is true.

        Args:
            baseurl:        Patchwork base URL.
            pname:          Patchwork project name.
            lpatch:         Last processed patch. Patch ID, if adding an XML
                            RPC-based interface. Patch timestamp, if adding a
                            REST-based interface. Can be omitted to
                            retrieve one from the database.
            apikey:         Patchwork REST API authentication token.
            skip:           List of additional regex patterns to skip in patch
                            names, case insensitive.
        """
        if self.restapi:
            pw = sktm.patchwork.skt_patchwork2(
                baseurl, pname, lpatch, apikey, skip
            )

            # FIXME Figure out the last patch first, then create the interface
            if lpatch is None:
                lcdate = self.db.get_last_checked_patch_date(baseurl,
                                                             pw.project_id)
                lpdate = self.db.get_last_pending_patch_date(baseurl,
                                                             pw.project_id)
                since = max(lcdate, lpdate)
                if since is None:
                    raise Exception("%s project: %s was never tested before, "
                                    "please provide initial patch id" %
                                    (baseurl, pname))
                pw.since = since
        else:
            pw = sktm.patchwork.skt_patchwork(
                baseurl, pname, int(lpatch) if lpatch else None, skip
            )

            # FIXME Figure out the last patch first, then create the interface
            if lpatch is None:
                lcpatch = self.db.get_last_checked_patch(baseurl,
                                                         pw.project_id)
                lppatch = self.db.get_last_pending_patch(baseurl,
                                                         pw.project_id)
                lpatch = max(lcpatch, lppatch)
                if lpatch is None:
                    raise Exception("%s project: %s was never tested before, "
                                    "please provide initial patch id" %
                                    (baseurl, pname))
                pw.lastpatch = lpatch
        self.pw.append(pw)

    # FIXME Fix the name, this function doesn't check anything by itself
    def check_baseline(self):
        """Submit a build for baseline."""
        build_id = self.jk.build(
            self.jobname,
            baserepo=self.baserepo,
            ref=self.baseref,
            baseconfig=self.cfgurl,
            makeopts=self.makeopts
        )
        self.pj.append((sktm.jtype.BASELINE, build_id, None))

        # Add this baseline test to the pendingjobs table
        self.db.add_pending_job(self.jobname, build_id)


    def filter_patchsets(self, series_summary_list):
        """
        Filter series, determining which ones are ready for testing, and
        which shouldn't be tested at all.

        Args:
            series_summary_list:  The list of summaries of series to filter.
        Returns:
            A tuple of series summary lists:
                - series ready for testing,
                - series which should not be tested
        """
        ready = []
        dropped = []

        if self.patch_filter:
            for series_summary in series_summary_list:
                argv = [self.patch_filter]
                if series_summary.cover_letter:
                    argv += ["--cover",
                             series_summary.cover_letter.get_mbox_url()]
                argv += series_summary.get_patch_mbox_url_list()
                # TODO Shell-quote
                cmd = " ".join(argv)
                logging.info("Executing patch filter command %s", cmd)
                # TODO Redirect output to logs
                status = subprocess.call(argv)
                if status == 0:
                    ready.append(series_summary)
                elif status == 1:
                    dropped.append(series_summary)
                elif status == 127:
                    raise Exception("Filter command %s failed" % (cmd))
                elif status < 0:
                    raise Exception("Filter command %s was terminated "
                                    "by signal %d" % (cmd, -status))
                else:
                    raise Exception("Filter command %s returned "
                                    "invalid status %d" % (cmd, status))
        else:
            ready += series_summary_list

        return ready, dropped

    def get_patch_info_from_url(self, interface, patch_url):
        """
        Retrieve patch info tuple.

        Args:
            interface: Interface of the Patchwork project the patch belongs to.
            patch_url: URL of the patch to retrieve info tuple for.

        Returns: Patch info tuple (patch_id, patch_name, patch_url, baseurl,
                                   project_id, patch_date).
        """
        match = re.match(r'(.*)/patch/(\d+)$', patch_url)
        if not match:
            raise Exception('Malformed patch url: %s' % patch_url)

        baseurl = match.group(1)
        patch_id = int(match.group(2))
        patch = interface.get_patch_by_id(patch_id)
        if patch is None:
            raise Exception('Can\'t get data for %s' % patch_url)

        logging.info('patch: [%d] %s', patch_id, patch.get('name'))

        if self.restapi:
            project_id = int(patch.get('project').get('id'))
        else:
            project_id = int(patch.get('project_id'))

        return (patch_id, patch.get('name'), patch_url, baseurl, project_id,
                patch.get('date').replace(' ', 'T'))

    def check_patchwork(self):
        """
        Submit and register Jenkins builds for series which appeared in
        Patchwork instances after their last processed patches, and for
        series which are comprised of patches added to the "pending" list
        in the database, more than 12 hours ago.
        """
        stablecommit = self.db.get_stable(self.baserepo)
        if not stablecommit:
            raise Exception("No known stable baseline for repo %s" %
                            self.baserepo)

        logging.info("stable commit for %s is %s", self.baserepo, stablecommit)
        # For every Patchwork interface
        for cpw in self.pw:
            series_list = list()
            # Get series summaries for all patches the Patchwork interface
            # hasn't seen yet
            new_series = cpw.get_new_patchsets()
            for series in new_series:
                logging.info("new series: %s", series.get_obj_url_list())
            series_ready, series_dropped = self.filter_patchsets(new_series)
            for series in series_ready:
                logging.info("ready series: %s", series.get_obj_url_list())
            for series in series_dropped:
                logging.info("dropped series: %s", series.get_obj_url_list())

                # Retrieve all data and save dropped patches in the DB
                patches = []
                for patch_url in series.get_patch_url_list():
                    patches.append(self.get_patch_info_from_url(cpw,
                                                                patch_url))

                self.db.commit_series(patches)

            series_list += series_ready
            # Add series summaries for all patches staying pending for
            # longer than 12 hours
            series_list += cpw.get_patchsets(
                self.db.get_expired_pending_patches(cpw.baseurl,
                                                    cpw.project_id,
                                                    43200)
            )
            # For each series summary
            for series in series_list:
                # (Re-)add the series' patches to the "pending" list
                self.db.set_patchset_pending(cpw.baseurl, cpw.project_id,
                                             series.get_patch_info_list())
                # Submit and remember a Jenkins build for the series
                self.pj.append((sktm.jtype.PATCHWORK,
                                self.jk.build(
                                    self.jobname,
                                    baserepo=self.baserepo,
                                    ref=stablecommit,
                                    baseconfig=self.cfgurl,
                                    message_id=series.message_id,
                                    subject=series.subject,
                                    emails=series.email_addr_set,
                                    patchwork=series.get_patch_url_list(),
                                    makeopts=self.makeopts),
                                cpw))
                logging.info("submitted message ID: %s", series.message_id)
                logging.info("submitted subject: %s", series.subject)
                logging.info("submitted emails: %s", series.email_addr_set)
                logging.info("submitted series: %s",
                             series.get_patch_url_list())

    def check_pending(self):
        """Check on jobs that were sent to Jenkins during the last sktm run."""
        # Get a list of pending Jenkins jobs
        pending_jobs = self.db.get_pending_jobs()

        if not pending_jobs:
            logging.info("No pending jobs to check -- exiting")
            return

        for pending_job in pending_jobs:
            pendingjob_id, job_name, build_id = pending_job
            logging.info("Checking job: %s (#%d)", job_name, build_id)

            # Come back and check on the job later if it is still running.
            if not self.jk.is_build_complete(job_name, build_id):
                logging.info(
                    "Job is still running: %s (#%d)", job_name, build_id
                )
                continue

            # Get the build status and check to see if it was aborted.
            result = self.jk.get_build_status(job_name, build_id)
            if result == 'ABORTED':
                logging.info(
                    "Test was aborted in Jenkins: %s (#%d)",
                    job_name,
                    build_id
                )
                # Remove the pending job and any associated patches.
                self.db.remove_pending_job(pendingjob_id)
                continue

            # Get a list of pending patches associated with this job.
            pending_patches = self.db.get_patches_for_job(pendingjob_id)

            # Was this a baseline test?
            if not pending_patches:
                logging.info(
                    "Baseline test completed: %s (#%d) [%s]",
                    job_name,
                    build_id,
                    result
                )
                # Update the database with the results of the baseline test.
                self.db.update_baseline(
                    self.baserepo,
                    self.jk.get_base_hash(job_name, build_id),
                    self.jk.get_base_commitdate(job_name, build_id),
                    self.jk.get_result(job_name, build_id),
                    build_id
                )
                self.db.remove_pending_job(pendingjob_id)
                return

            # If we made it this far, we are working on a patchwork test.
            logging.info(
                "Patchwork test completed: %s (#%d) [%s]",
                job_name,
                build_id,
                result
            )

            # Clean up the list of pending patches.
            self.db.commit_tested([x[1] for x in pending_patches])
