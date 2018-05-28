# Copyright (c) 2017-2018 Red Hat, Inc. All rights reserved. This copyrighted
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


class DirectRun(object):
    """Direct test run"""

    def __init__(self, work_dir, work_url, skt_work_dir,
                 baserepo, baseref, baseconfig,
                 message_id, subject, emails,
                 patch_url_list, makeopts)
        """
        Initialize a direct test run.

        Args:
            dir:            Directory to run in.
            url:            URL through which the directory is shared.
            skt_dir:        Skt work directory to use.
            baserepo:       Baseline Git repo URL.
            baseref:        Baseline Git reference.
            baseconfig:     Kernel configuration URL.
            message_id:     Value of the "Message-Id" header of the e-mail
                            message representing the patchset, or None if
                            unknown.
            subject:        Subject of the message representing the patchset,
                            or None if unknown.
            emails:         Set of e-mail addresses involved with the patchset
                            to send notifications to.
            patch_url_list: List of URLs pointing to patches to apply, in the
                            order they should be applied in.
            makeopts:       String of extra arguments to pass to the build's
                            make invocation.

        """
        self.dir = dir
        self.url = url
        self.skt_dir = skt_dir
        self.baserepo = baserepo
        self.baseref = baseref
        self.baseconfig = baseconfig
        self.message_id = message_id
        self.subject = subject
        self.emails = emails
        self.patch_url_list = patch_url_list
        self.makeopts = makeopts

    def start():
        """
        Start the run.
        """
        # Create directory for JUnit results
        self.dir_junit = os.path.join(self.dir, "junit")
        os.mkdir(self.dir_junit)
        # Create directory for build artifacts
        self.dir_build = os.path.join(self.dir, "build")
        os.mkdir(self.dir_build)
        # Format URL for build artifacts
        self.url_build =
            urlparse.urljoin(self.url, os.path.basename(self.dir_build))
        # Start skt
        self.started = True

    def is_started():
        """
        Check if the run is started.

        Returns:
            True if the run is started, false otherwise.
        """

    def abort():
        """
        Abort a run: stop the run, if started, and mark it aborted.
        """
    def is_finished():
        """
        Check if the run is finished.

        Returns:
            True if the run is finished, false otherwise.
        """


class Direct(object):
    """Direct test run scheduler"""

    def __init__(self, skt_dir, public_hostname, port,
                 beaker_job_template, parallel_run_num):
        """
        Initialize a direct test run scheduler.
        """
        # Scheduler data directory
        self.dir = None
        # HTTP server PID
        self.httpd_pid = None
        # Scheduler public data URL (as shared by the HTTP server)
        self.url = None
        # Skt work directory to use
        self.skt_dir = skt_dir
        # Hostname the published artifacts should be accessible at
        self.public_hostname = public_hostname
        # Port the published artifacts should be accessible at
        self.port = port
        # Path to the Beaker job XML template to supply to skt
        self.beaker_job_template = beaker_job_template
        # Maximum number of parallel runs
        self.parallel_run_num = parallel_run_num
        # Next run ID
        self.run_id = 0
        # Run ID -> object map
        self.run_map = {}

        # Create the scheduler directory
        self.dir = tempfile.mkdtemp(suffix="sktm_runs_")
        # Start an HTTP server for serving artifacts
        self.httpd_pid = os.fork()
        if self.httpd_pid == 0:
            os.chdir(self.dir)
            httpd = BaseHTTPServer.HTTPServer(
                        ("", port),
                        SimpleHTTPServer.SimpleHTTPRequestHandler)
            # TODO Print port number we're listening on, e.g.
            # print(httpd.socket.getsockname()[1])
            httpd.serve_forever()
            os._exit(0)
        # TODO Read and update the port in case it was zero
        # TODO That will also ensure the server is functional
        # Format our public URL
        self.url = "http://" + self.public_hostname + ":" + self.port

    def __del__():
        """
        Cleanup a direct test run scheduler.
        """
        if self.httpd_pid:
            os.kill(self.httpd_pid)
        if self.dir:
            shutil.rmtree(self.dir)

    def get_base_commitdate(self, run_id):
        """
        Get base commit's committer date of the specified completed run.
        Wait for the run to complete, if it hasn't yet.

        Args:
            run_id:    Run ID.

        Return:
            The epoch timestamp string of the committer date.
        """

    def get_base_hash(self, run_id):
        """
        Get base commit's hash of the specified completed run.
        Wait for the run to complete, if it hasn't yet.

        Args:
            run_id:    Run ID.

        Return:
            The base commit's hash string.
        """

    def get_patch_url_list(self, run_id):
        """
        Get the list of Patchwork patch URLs for the specified completed
        run. Wait for the run to complete, if it hasn't yet.

        Args:
            run_id:    Run ID.

        Return:
            The list of Patchwork patch URLs, in the order the patches should
            be applied in.
        """

    def get_result_url(self, run_id):
        """
        Get the URL of the web representation of the specified run.

        Args:
            run_id:    Run ID.

        Result:
            The URL of the run result.
        """

    def get_result(self, run_id):
        """
        Get result code (sktm.misc.tresult) for the specified run.
        Wait for the run to complete, if it hasn't yet.

        Args:
            run_id:    Run ID.

        Result:
            The run result code (sktm.misc.tresult).
        """

    def __update():
        """
        Update run status.
        """
        # Start with the maximum allowed run number
        parallel_run_num = self.parallel_run_num
        # Subtract runs in progress
        for run_id, run in self.run_map.items():
            if run.is_active():
                parallel_run_num -= 1
        # Fill up with new jobs
        while parallel_run_num > 0:
            for run_id, run in self.run_map.items():
                if not run.is_complete():
                    run.start()

    def submit(self, baserepo=None, baseref=None, baseconfig=None,
               message_id=None, subject=None, emails=set(), patch_url_list=[],
               makeopts=None):
        """
        Submit a run.

        Args:
            baserepo:       Baseline Git repo URL.
            baseref:        Baseline Git reference to test.
            baseconfig:     Kernel configuration URL.
            message_id:     Value of the "Message-Id" header of the e-mail
                            message representing the patchset, or None if
                            unknown.
            subject:        Subject of the message representing the patchset,
                            or None if unknown.
            emails:         Set of e-mail addresses involved with the patchset
                            to send notifications to.
            patch_url_list: List of URLs pointing to patches to apply, in the
                            order they should be applied in.
            makeopts:       String of extra arguments to pass to the build's
                            make invocation.

        Returns:
            Submitted run number.
        """
        # Grab next run ID
        run_id = self.run_id
        # Create a run directory
        run_dir = os.path.join(self.dir, run_id)
        os.mkdir(run_dir)
        # Format a run URL
        run_url = urlparse.urljoin(self.url, run_id)
        # Create a run
        run = DirectRun(dir=run_dir,
                        url=run_url,
                        skt_dir=self.skt_dir,
                        baserepo=baserepo,
                        baseref=baseref,
                        baseconfig=baseconfig,
                        message_id=message_id,
                        subject=subject,
                        emails=emails,
                        patch_url_list=patch_url_list,
                        makeopts=makeopts)
        self.job_map[run_id] = run
        # Submitted, move onto next ID
        self.run_id += 1
        # Update run status.
        self.__update()
        return run_id

    def is_run_complete(self, run_id):
        """
        Check if a run is complete.

        Args:
            run_id:    Run ID.

        Return:
            True if the run is complete.
        """
