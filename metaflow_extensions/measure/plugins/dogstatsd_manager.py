import os
import sys
import tempfile
import socket
import json
import time
import random
import hashlib
import fcntl
import platform
import subprocess

import requests

from . import datadog as dd
from .measure import MeasurementBackend, register_backend

BASE = "https://outerbounds-metaflow-public.s3.us-west-2.amazonaws.com/"
BINARIES = {
    ("Darwin", "arm64"): "dogstatsd-darwin-arm64",
    ("Linux", "x86_64"): "dogstatsd-linux-amd64",
}

# wait for this many seconds when another process
# is launching the daemon
WAIT_TO_DOWNLOAD = 7
WAIT_TO_START = 3

DOWNLOAD_ATTEMPTS = 5
CONNECT_ATTEMPTS = 10
SOCK_NAME = "metaflow_dogstatsd"
BINARY_NAME = "metaflow-dogstatsd"
DOGSTATSD_MAX_AGE_HOURS = 24


class DogMeasure(MeasurementBackend):
    def gauge(self, name, value, tags=None):
        dd.statsd.gauge(name, value, tags=tags)

    def increment(self, name, value=1, tags=None):
        dd.statsd.increment(name, value, tags=tags)

    def decrement(self, name, value=1, tags=None):
        dd.statsd.decrement(name, value, tags=tags)

    def distribution(self, name, value, tags=None):
        dd.statsd.distribution(name, value, tags=tags)

class DogStatsD:
    def __init__(
        self,
        api_key=None,
        tags=None,
        datadog_config=None,
        verbose=False,
        debug_daemon=False,
    ):
        self.debug_daemon = debug_daemon
        self.verbose = verbose
        self.tags = [] if tags is None else tags
        self.api_key = api_key
        self.datadog_config = {} if datadog_config is None else datadog_config

        # we need a separate daemon for every unique set of DD config vars and api_key
        # We identify each daemon process by a config fingerprint
        config_str = json.dumps(list(sorted(self.datadog_config.items())) + [api_key])
        config_id = hashlib.sha1(config_str.encode("utf-8")).hexdigest()[:16]
        self._log(f"The ID of this Dogstatsd is {config_id}")

        root = tempfile.gettempdir()
        self.pid_path = os.path.join(root, f"{SOCK_NAME}-{config_id}.pid")
        self.socket_path = os.path.join(root, f"{SOCK_NAME}-{config_id}.sock")
        self.dogstatsd_path = os.path.join(root, BINARY_NAME)

        if api_key:
            self._init()
            if (
                self._binary_exists() or self._try_download()
            ) and self._attempt_connect():
                # dogstatsd seems to be up and running, use it as a measurement backend
                self._log("Datadog ready!")
                register_backend(DogMeasure())
            else:
                self._log("Measurements not sent to Datadog due to previous errors")
        else:
            self._warn(
                "api_key missing. Specify @datadog(api_key=...) or "
                "DD_API_KEY environment variable"
            )

    def flush(self):
        dd.statsd.flush()

    def _log(self, msg):
        if self.verbose:
            print(f"[@datadog] {msg}")

    def _warn(self, msg):
        print(
            f"DATADOG WARNING: {msg}. Metrics are not sent to Datadog!", file=sys.stderr
        )

    def _init(self):
        # NOTE: all the file descriptor / lock machinery below exists
        # below to account for the fact that many instances of this class
        # run in parallel across processes (think a foreach)
        self.prev_pid = None
        if os.path.exists(self.pid_path):
            try:
                with open(self.pid_path) as f:
                    self.prev_pid = int(f.read())
            except:
                pass
        else:
            # make sure the file exists but don't truncate
            # an existing file
            try:
                with open(self.pid_path, "x") as f:
                    pass
            except:
                pass

        # our lock stays alive as long as this instance stays alive
        self.pid_fd = open(self.pid_path, "r+")
        try:
            fcntl.flock(self.pid_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.iam_leader = True
            self._log("I am the leader")
        except:
            self.iam_leader = False
            self._log("I am not the leader")

    def _binary_exists(self):
        if os.path.exists(self.dogstatsd_path):
            t = os.path.getctime(self.dogstatsd_path)
            self._log(f"Dogstatsd binary found at {self.dogstatsd_path}")
            if (time.time() - t) / 3600.0 < DOGSTATSD_MAX_AGE_HOURS:
                self._log(f"Dogstatsd binary is fresh enough")
                return True
            else:
                self._log(f"Dogstatsd binary is too old. Need a new one")
        else:
            self._log(f"Dogstatsd binary not found at {self.dogstatsd_path}")

    def _try_download(self):
        if not self.iam_leader:
            self._log(f"Waiting for the leader to download a Dogstatsd binary")
            time.sleep(WAIT_TO_DOWNLOAD + random.random())
            return True

        binary_id = (platform.system(), platform.machine())
        self._log("System profile: %s / %s" % binary_id)
        if binary_id not in BINARIES:
            self._warn(f"Dogstatsd binary is not available for your system {binary_id}")
            return False
        else:
            url = BASE + BINARIES[binary_id]
            exc = None
            self._log(f"Downloading Dogstatsd from {url}")
            for i in range(DOWNLOAD_ATTEMPTS):
                try:
                    resp = requests.get(url)
                    if resp.ok:
                        with tempfile.NamedTemporaryFile(
                            prefix=BINARY_NAME, mode="wb", delete=False
                        ) as tmp:
                            tmp.write(resp.content)
                            tmp.flush()
                            os.chmod(tmp.name, 755)
                            os.rename(tmp.name, self.dogstatsd_path)
                        self._log(
                            f"Dogstatsd is now available at {self.dogstatsd_path}"
                        )
                        return True
                    elif 400 < resp.status_code < 500:
                        self._warn(
                            f"Could not download Dogstatsd binary (code {resp.status_code})."
                            " Not retrying"
                        )
                        return False
                    resp.raise_for_status()
                except Exception as ex:
                    self._log(f"Downloading Dogstatsd failed: {ex}")
                    exc = str(ex)
                    time.sleep(2**i + random.random())
            self._warn(f"Downloading Dogstatsd binary failed: {exc}")

    def _try_start_daemon(self):
        def _start_process():
            env = {
                "DD_DOGSTATSD_SOCKET": self.socket_path,
                "DD_LOG_FILE": "/dev/null",
                "DD_API_KEY": self.api_key,
            }
            env.update(self.datadog_config)
            if self.debug_daemon:
                opt = {}
            else:
                opt = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            self._log(f"Starting Dogstatsd at {self.dogstatsd_path}")
            proc = subprocess.Popen([self.dogstatsd_path, "start"], env=env, **opt)
            self._log(f"Dogstatsd pid is {proc.pid}")
            time.sleep(1)
            proc.poll()
            if proc.returncode is None:
                self._log("Dogstatsd seems to have started ok - still running")
                return proc.pid
            else:
                self._log(
                    "Dogstatsd did not start properly - exit code {proc.exitcode}"
                )
                return None

        if self.iam_leader:
            # I am the leader
            try:
                if self.prev_pid:
                    # try to kill an existing daemon
                    # due to flock() above, daemon that belongs
                    # to any alive task (process) can't be killed
                    self._log(f"Killing previous Dogstatsd at {self.prev_pid}")
                    os.kill(self.prev_pid, 9)
                    # give the process some time to die
                    time.sleep(1 + random.random())
            except:
                pass
            # Let's start the daemon
            pid = _start_process()
            if pid is None:
                return False
            else:
                self.pid_fd.seek(0)
                self.pid_fd.write(str(pid))
                self.pid_fd.flush()
                return True
        else:
            self._log("Waiting for the leader to start the daemon")
            # I am not the leader, bailing out after giving
            # the leader a bit of time to start the daemon
            time.sleep(WAIT_TO_START + random.random())
            return True

    def _is_daemon_alive(self):
        client = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            self._log(f"Trying to connect the daemon at {self.socket_path}")
            # this connection will fail if the daemon is not alive
            client.connect(self.socket_path)
            # daemon is alive, close connection..
            client.close()
            # ..and initialize the datadog client
            options = {
                "statsd_socket_path": self.socket_path,
                "statsd_constant_tags": self.tags,
            }
            dd.initialize(**options)
            self._log("Connection ok!")
            return True
        except Exception as ex:
            self._log(f"Could not connect the daemon: {ex}")
            return False

    def _attempt_connect(self):
        def try_connect():
            for i in range(CONNECT_ATTEMPTS):
                if self._is_daemon_alive():
                    return True
                time.sleep(1 + random.random())

        if os.path.exists(self.socket_path):
            # 1. fast path: file exists, let's try to connect
            if try_connect():
                # happy case - existing connection works
                return True
        # 2. file doesn't exist or connection failed,
        # let's try to start a new daemon
        if self._try_start_daemon():
            # 3. let's try to connect again
            if try_connect():
                # new daemon worked
                return True
            else:
                # FAIL: couldn't establish a connection!
                self._warn(
                    f"Could not establish connection to "
                    "dogstatsd at {self.socket_path}"
                )
                return False
        else:
            self._warn(f"Could not start the daemon {self.dogstatsd_path}")
            return False


if __name__ == "__main__":
    import measure

    DogStatsD(sys.argv[1], verbose=True)
    with measure.TimeDistribution("mtest.distr"):
        time.sleep(5)
