import time

_backends = []


def register_backend(backend):
    _backends.append(backend)


def gauge(name, value, tags=None):
    for b in _backends:
        b.gauge(name, value, tags=tags)


def increment(name, value=1, tags=None):
    for b in _backends:
        b.increment(name, value, tags=tags)


def decrement(name, value=1, tags=None):
    for b in _backends:
        b.decrement(name, value, tags=tags)


def distribution(name, value, tags=None):
    for b in _backends:
        b.distribution(name, value, tags=tags)


class TimeDistribution:
    def __init__(self, name, tags=None, resolution="ms"):
        self.res = {"ms": 1000, "s": 1, "m": 1 / 60.0}.get(resolution, 1)
        self.name = name
        self.tags = tags

    def __enter__(self):
        self.start = time.time()

    def __exit__(self, *exc):
        val = round(self.res * (time.time() - self.start))
        distribution(self.name, val, tags=self.tags)


class MeasurementBackend:
    def gauge(name, value, timestamp=None, tags=None):
        pass

    def increment(self, name, value, tags=None):
        pass

    def decrement(self, name, value, tags=None):
        pass

    def distribution(name, value, tags=None):
        pass

    def flush(self):
        pass
