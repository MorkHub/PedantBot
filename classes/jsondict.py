import json
import inspect
serializable_types = (dict, list, tuple, str, int, float, bool, None.__class__)


class JSONDict(object):
    _ignore = []

    def __init__(self, **kwargs):
        for kwarg in kwargs:
            setattr(self, kwarg, kwargs.get(kwarg))

    def __contains__(self, item):
        return hasattr(self, item)

    def to_dict(self, simple=False):
        temp = {}
        for (key, value) in inspect.getmembers(self, lambda a: not(inspect.isroutine(a))):
            if key == '_ignore':
                continue
            if simple and key in self._ignore:
                continue
            if key.startswith('__'):
                continue

            if not isinstance(value, serializable_types):
                if hasattr(value, 'to_json'):
                    value = value.to_dict(simple)
                elif hasattr(value, '__str__'):
                    value = str(value)
                else:
                    continue

            temp[key] = value
        return temp

    def to_json(self, simple=False):
        return json.dumps(
            self.to_dict(simple),
            default=lambda x: self.get_dict(x, simple)
        )

    def __repr__(self):
        cls = self.__class__.__name__
        if hasattr(self, 'name'):
            return "{}: {}".format(cls, self.name)
        else:
            return cls

    def __str__(self):
        return self.to_json()

    @staticmethod
    def get_dict(obj, simple=False):
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, 'to_dict'):
            return obj.to_dict(simple)
        if hasattr(obj, '__dict__'):
            return obj.__dict__
        return {}
