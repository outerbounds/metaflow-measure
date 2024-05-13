from setuptools import setup, find_namespace_packages

version = "0.0.1"

setup(
    name="metaflow-measure",
    version=version,
    description="Measure metrics and timing in Metaflow steps, send them optionally to Datadog or other backends."
    author="Outerbounds",
    author_email="hello@outerbounds.co",
    packages=find_namespace_packages(include=["metaflow_extensions.*"]),
    py_modules=[
        "metaflow_extensions",
    ],
    install_requires=[
         "metaflow"
    ]
)
