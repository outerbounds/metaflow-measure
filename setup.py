from setuptools import setup, find_namespace_packages

version = "0.0.2"

setup(
    name="metaflow-measure",
    version=version,
    description="Measure metrics and timings in Metaflow steps and send them optionally to Datadog or other backends",
    author="Outerbounds",
    author_email="hello@outerbounds.co",
    packages=find_namespace_packages(include=["metaflow_extensions.*"]),
    py_modules=[
        "metaflow_extensions",
    ]
)
