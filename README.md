
# Metrics and Measurements in Metaflow steps

This extension introduces a `measure` API that allows you to send custom
metrics and measure execution times in your Metaflow steps.

## Key features

 - Very simple instrumentation API: Measure your code with a few
   lines of Python.

 - Separation between the instrumentation API and the metrics
   backends: Instrument your code with the `measure` API,
   record metrics locally during development, and enable a
   production backend like Datadog during deployment-time.

 - Works locally and on `@kubernetes` and `@batch` with no
   changes in the code.

 - Native integration with Metaflow: Metrics are tagged
   with Metaflow run ID, step names, `@project` branches
   etc. so you can drill into details.

 - Works at scale: Uses aggregators like `dogstatsd` to
   avoid overloading backend APIs.

 - No extra dependencies: `@datadog` installs the
   `dogstatsd` on the fly, so it works in any execution
   environment.

## API

The `measure` module exposes [`statsd`-style measurement
functions](https://docs.datadoghq.com/metrics/custom_metrics/dogstatsd_metrics_submission/):
`gauge`, `increment`, and `decrement`.

Optionally, all `measure` functions take a keyword argument
`tags` which takes a list of custom tags (strings) to be
associated with the measurement.

### Basic Metrics

```python
from metaflow.plugins import measure

# record a gauge metric
measure.gauge('mymetric', value)

# record a gauge metric
measure.increment('mymetric', value)

# record a gauge metric
measure.decrement('mymetric', value)
```

### Distributions

In addition, `measure` provides `distribution` which allows
you to measure distributions of values (e.g. p50, p95 etc) relying
on server-side aggregation for accuracy.

```python
from metaflow.plugins import measure

# record a distribution metric
measure.distribution('mydistribution', value)

```

For convenience, the API provides a context manager that
allows you to measure the execution time of a code block easily.

```python
from metaflow.plugins import measure

with measure.TimeDistribution('mytiming'):
   some_time_consuming_function()
```

# Supported Backends

Currently, the following backends are supported

## `@datadog`

Add `@datadog` in your steps to send measurements to Datadog.
Typically, you would instrument your code with `measure` and
then enable Datadog on the fly with

```
python measureflow.py run --with datadog:api_key=$API_KEY
```

### Authentication

You can provide the `api_key` in the decorator
```
@datadog(api_key=MY_KEY)
```
or on the command line
```
--with datadog:api_key=$API_KEY
```
or set the environment variable `DD_API_KEY` via `@secrets` or
`@environment`.

### Tags

The `@datadog` decorator adds various Metaflow-related tags
to all metrics, prefixed with `metaflow_`. You can disable
this with
```
@datadog(include_metaflow_tags=False)
```
and/or set custom tags to be associated with all measurements as
```
@datadog(tags=['mytag'])
```

### Debugging

To debug connectivity issues in Datadog, set
```
@datadog(verbose=True, debug_daemon=True)
```

## Example

Run the following flow to see the extension in action.

```python
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
```

If you run this flow as
```
export DD_API_KEY=my_datadog_key
python measureflow.py run
```
only the measurements from the `start` step will be sent to Datadog,
thanks to the `@datadog` decorator. The `end` step executes with `measure`
calls, but they are not sent anywhere as no backend has been configured
for the step.

To test sending all metrics to Datadog, add `@datadog` to the `end` step
or run the flow as
```
python measureflow.py run --with datadog
```

Test the code in the cloud
```
python measureflow.py run --with kubernetes --with datadog:api_key=$DD_API_KEY
```
(or `--with batch`)


