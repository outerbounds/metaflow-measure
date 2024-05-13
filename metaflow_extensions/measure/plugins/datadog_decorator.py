import os
import time

from metaflow.decorators import StepDecorator
from metaflow.exception import MetaflowException
from metaflow.metaflow_config import MAX_ATTEMPTS
from metaflow import current

from .dogstatsd_manager import DogStatsD


class DatadogDecorator(StepDecorator):
    name = "datadog"
    defaults = {
        "api_key": "",
        "verbose": None,
        "tags": [],
        "include_metaflow_tags": True,
        "debug_daemon": None,
        "datadog_config": None,
        "wait_to_flush": 20
    }

    def task_pre_step(
        self,
        step_name,
        task_datastore,
        metadata,
        run_id,
        task_id,
        flow,
        graph,
        retry_count,
        max_user_code_retries,
        ubf_context,
        inputs,
    ):
        if self.attributes["api_key"]:
            api_key = self.attributes["api_key"]
        else:
            api_key = os.environ.get("DD_API_KEY", "")

        tags = self.attributes["tags"]
        if bool(self.attributes["include_metaflow_tags"]):
            runtime = os.environ.get("METAFLOW_RUNTIME_NAME", "dev")
            tags += [
                f"metaflow_runtime:{runtime}",
                f"metaflow_flow:{current.flow_name}",
                f"metaflow_runid:{current.run_id}",
                f"metaflow_step:{current.step_name}",
                f"metaflow_user:{current.username}",
            ]
            if getattr(current, "project_name", None):
                tags += [
                    f"metaflow_project:{current.project_name}",
                    f"metaflow_branch:{current.branch_name}",
                ]
                if current.is_production:
                    tags += ["metaflow_production"]

        # NOTE: it is important that we keep the DogStatsD instance
        # alive during the exeuction of a task, as it keeps the dogstatsd
        # leader stable through a lockfile
        self.dog = DogStatsD(
            api_key=api_key,
            tags=tags,
            verbose=bool(self.attributes["verbose"]),
            debug_daemon=bool(self.attributes["debug_daemon"]),
            datadog_config=self.attributes["datadog_config"],
        )

    def task_finished(
        self, step_name, flow, graph, is_task_ok, retry_count, max_user_code_retries
    ):
        self.dog.flush()
        # by default dogstatsd flushes its buffers every 10 seconds. Hence
        # to ensure that last metrics get sent to DD, in remote environments where
        # the container dies immediately after the task, we need to wait at least
        # 10 seconds in the end.

        # It would be great if Dogstatsd had a signal or something to support
        # flushing on demand
        #
        # set @datadog(wait_to_flush=0) to disable the extra wait time
        if any(k in os.environ for k in ('AWS_BATCH_JOB_ID',\
                                         'METAFLOW_KUBERNETES_POD_ID')):
            time.sleep(int(self.attributes['wait_to_flush']))

