import os, time

from metaflow import FlowSpec, step, datadog
from metaflow.plugins import measure

class MeasureFlow(FlowSpec):

    @datadog
    @step
    def start(self):
        for i in range(10):
            measure.increment('mftest.test_metric')
            time.sleep(1)
        with measure.TimeDistribution('mftest.slow_operation', tags=['custom_tag']):
            time.sleep(10)
        self.next(self.end)

    @step
    def end(self):
        # this metric is not sent anywhere by default,
        # unless you add @datadog or another backend
        measure.gauge('mftest.my_gauge', 42)

if __name__ == '__main__':
    MeasureFlow()
