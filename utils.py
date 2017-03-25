from __future__ import print_function
import functools
import inspect
import json
import logging.config
import re

try:
    from UserDict import IterableUserDict as UserDict
    from UserList import UserList
except ImportError:
    from collections import UserDict, UserList
try:
    basestring
except NameError:
    basestring = str
from collections import Sized, defaultdict, Mapping, Sequence
from datetime import datetime, date, time
from decimal import Decimal
from fractions import Fraction
from numbers import Rational
from itertools import islice
from json.encoder import JSONEncoder
from pprint import pprint
from time import sleep


def _helpful_dict_error(d, key):
    raise KeyError('Tried to access %r, only keys are: %s' % (key, str(sorted(d.keys()))[:1000]))


def helpful_error_dict_get(d, key):
    """
    >>> d = {1: 2, 3: 4}
    >>> helpful_error_dict_get(d, 'a')
    Traceback (most recent call last):
    ...
    KeyError: "Tried to access 'a', only keys are: [1, 3]"
    """
    try:
        return d[key]
    except KeyError:
        _helpful_dict_error(d, key)


class HelpfulErrorDict(UserDict):
    """
    >>> d = HelpfulErrorDict({1: 2, 3: 4})
    >>> d[1]
    2
    >>> d['a']
    Traceback (most recent call last):
    ...
    KeyError: "Tried to access 'a', only keys are: [1, 3]"
    """

    __missing__ = _helpful_dict_error


def helpful_error_list_get(lst, index):
    """
    >>> helpful_error_list_get([1, 2, 3], 1)
    2
    >>> helpful_error_list_get([1, 2, 3], 4)
    Traceback (most recent call last):
    ...
    IndexError: Tried to access 4, length is only 3
    """
    try:
        return lst[index]
    except IndexError:
        raise IndexError('Tried to access %r, length is only %r' % (index, len(lst)))


class HelpfulErrorList(UserList):
    """
    >>> lst = HelpfulErrorList([1, 2, 3])
    >>> lst[1]
    2
    >>> lst[4]
    Traceback (most recent call last):
    ...
    IndexError: Tried to access 4, length is only 3
    """

    def __getitem__(self, item):
        return helpful_error_list_get(self.data, item)


def only(it):
    """
    >>> only([7])
    7
    >>> only([1, 2])
    Traceback (most recent call last):
    ...
    AssertionError: Expected one value, found 2
    >>> only([])
    Traceback (most recent call last):
    ...
    AssertionError: Expected one value, found 0
    >>> from itertools import repeat
    >>> only(repeat(5))
    Traceback (most recent call last):
    ...
    AssertionError: Expected one value, found several
    >>> only(repeat(5, 0))
    Traceback (most recent call last):
    ...
    AssertionError: Expected one value, found 0
    """

    if isinstance(it, Sized):
        if len(it) != 1:
            raise AssertionError('Expected one value, found %s' % len(it))
        return it[0]

    lst = tuple(islice(it, 2))
    if len(lst) == 0:
        raise AssertionError('Expected one value, found 0')
    if len(lst) > 1:
        raise AssertionError('Expected one value, found several')
    return lst[0]


class DoctestLogger(object):
    """
    Simple fake logger for use in doctests which stores logs to be printed whenever.
    This is because doctests don't support output and exceptions at the same time.
    """

    def __init__(self):
        self.logs = []

    def error(self, message, *args):
        self.logs.append(message % args)

    def print_logs(self):
        print('\n'.join(self.logs))


class PrintingLogger(object):
    @staticmethod
    def warn(message, *args):
        print(message % args)


def retry(num_attempts=3, exception_class=Exception, log=None, sleeptime=1):
    """
    >>> def fail():
    ...     runs[0] += 1
    ...     {}[1]
    >>> runs = [0]; retry(sleeptime=0)(fail)()
    Traceback (most recent call last):
    ...
    KeyError: 1
    >>> runs
    [3]
    >>> runs = [0]; retry(2, sleeptime=0)(fail)()
    Traceback (most recent call last):
    ...
    KeyError: 1
    >>> runs
    [2]
    >>> runs = [0]; retry(exception_class=IndexError, sleeptime=0)(fail)()
    Traceback (most recent call last):
    ...
    KeyError: 1
    >>> runs
    [1]
    >>> logger = DoctestLogger()
    >>> runs = [0]; retry(log=logger, sleeptime=0)(fail)()
    Traceback (most recent call last):
    ...
    KeyError: 1
    >>> runs
    [3]
    >>> logger.print_logs()
    Failed with error KeyError(1,), trying again
    Failed with error KeyError(1,), trying again
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            for i in range(num_attempts):
                try:
                    return func(*args, **kwargs)
                except exception_class as e:
                    if i == num_attempts - 1:
                        raise
                    else:
                        if log:
                            log.error('Failed with error %r, trying again', e)
                        sleep(sleeptime)

        return wrapper

    return decorator


def strip_optional_prefix(string, prefix, log=None):
    """
    >>> strip_optional_prefix('abcdef', 'abc')
    'def'
    >>> strip_optional_prefix('abcdef', '123')
    'abcdef'
    >>> strip_optional_prefix('abcdef', '123', PrintingLogger())
    String starts with 'abc', not '123'
    'abcdef'
    """
    if string.startswith(prefix):
        return string[len(prefix):]
    if log:
        log.warn('String starts with %r, not %r', string[:len(prefix)], prefix)
    return string


def strip_required_prefix(string, prefix):
    """
    >>> strip_required_prefix('abcdef', 'abc')
    'def'
    >>> strip_required_prefix('abcdef', '123')
    Traceback (most recent call last):
    ...
    AssertionError: String starts with 'abc', not '123'
    """
    if string.startswith(prefix):
        return string[len(prefix):]
    raise AssertionError('String starts with %r, not %r' % (string[:len(prefix)], prefix))


def ensure_list_if_string(x):
    """
    >>> assert (ensure_list_if_string(['abc', 'def', '123']) ==
    ...         ensure_list_if_string('abc,def,123') ==
    ...         ensure_list_if_string('abc def 123') ==
    ...         ensure_list_if_string(', abc , def , 123  , ,') ==
    ...         ['abc', 'def', '123'])
    """
    if isinstance(x, basestring):
        x = list(filter(None, re.split('[,\s]+', x)))
    return x


def setup_quick_console_logging(debug=False):
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'default': {
                'format': '%(asctime)s.%(msecs)03d %(levelname)8s | %(name)s.%(funcName)s:%(lineno)-4d | %(message)s',
                'datefmt': '%m-%d %H:%M:%S'
            },
        },
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'default',
            },
        },
        'loggers': {
            '': {
                'handlers': ['console'],
                'level': 'DEBUG' if debug else 'INFO',
            }
        }
    })


def select_keys(d, keys, helpful_error=True):
    """
    >>> d = dict(a=1, b=2, c=3)
    >>> print(json.dumps(select_keys(d, 'a c'), sort_keys=True))
    {"a": 1, "c": 3}
    >>> select_keys(d, 'a d')
    Traceback (most recent call last):
    ...
    KeyError: "Tried to access 'd', only keys are: ['a', 'b', 'c']"
    >>> select_keys(d, 'a d', helpful_error=False)
    Traceback (most recent call last):
    ...
    KeyError: 'd'
    """
    keys = ensure_list_if_string(keys)
    if helpful_error:
        return {k: helpful_error_dict_get(d, k) for k in keys}
    else:
        return {k: d[k] for k in keys}


class _MagicPrinter(object):
    """
    >>> a = 'hello world how are you today'
    >>> b = [{1: 2}, a, [3] * 20]
    >>> magic_print('a b', x=1+2)
    <BLANKLINE>
    =================== a : ===================
    <BLANKLINE>
    'hello world how are you today'
    <BLANKLINE>
    <BLANKLINE>
    =================== b : ===================
    <BLANKLINE>
    [{1: 2},
     'hello world how are you today',
     [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]]
    <BLANKLINE>
    <BLANKLINE>
    =================== x : ===================
    <BLANKLINE>
    3
    <BLANKLINE>
    >>> magic_print.a.b  # doctest:+ELLIPSIS
    <BLANKLINE>
    =================== a : ===================
    <BLANKLINE>
    'hello world how are you today'
    <BLANKLINE>
    <BLANKLINE>
    =================== b : ===================
    <BLANKLINE>
    [{1: 2},
     'hello world how are you today',
     [3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3]]
    <BLANKLINE>
    <__main__._MagicPrinter object at ...>
    """

    @staticmethod
    def _print_variable(name):
        value = helpful_error_dict_get(inspect.currentframe().f_back.f_back.f_locals, name)
        _MagicPrinter._print_named_value(name, value)

    @staticmethod
    def _print_named_value(name, value):
        print('\n=================== %s : ===================\n' % name)
        pprint(value)
        print('')

    def __getattr__(self, item):
        try:
            self._print_variable(item)
        except KeyError as e:
            raise AttributeError(e.message)
        return self

    def __call__(self, names, **kwargs):
        for name in ensure_list_if_string(names):
            self._print_variable(name)
        for name, value in kwargs.items():
            self._print_named_value(name, value)


magic_print = _MagicPrinter()


def group_by_key_func(iterable, key_func):
    """
    Create a dictionary from an iterable such that the keys are the result of evaluating a key function on elements
    of the iterable and the values are lists of elements all of which correspond to the key.

    >>> dict(group_by_key_func("a bb ccc d ee fff".split(), len))  # the dict() is just for looks
    {1: ['a', 'd'], 2: ['bb', 'ee'], 3: ['ccc', 'fff']}
    >>> dict(group_by_key_func([-1, 0, 1, 3, 6, 8, 9, 2], lambda x: x % 2))
    {0: [0, 6, 8, 2], 1: [-1, 1, 3, 9]}
    """
    result = defaultdict(list)
    for item in iterable:
        result[key_func(item)].append(item)
    return result


def setattrs(obj, **kwargs):
    """
    >>> class Data(object): pass
    >>> data = Data()
    >>> setattrs(data, a=1, b=2)  # doctest:+ELLIPSIS
    <__main__.Data object at ...>
    >>> data.a
    1
    >>> data.b
    2
    """
    for key, value in kwargs.items():
        setattr(obj, key, value)
    return obj


def string_to_file(string, path):
    with open(path, 'w') as f:
        f.write(string)


def file_to_string(path):
    with open(path, 'r') as f:
        return f.read()


def json_to_file(obj, path):
    string_to_file(json.dumps(obj), path)


def file_to_json(path):
    return json.loads(file_to_string(path))


def pretty_table(rows, header=None):
    """
    Returns a string with a simple pretty table representing the given rows.
    Rows can be:
     - Sequences such as lists or tuples
     - Mappings such as dicts
     - Any object with a __dict__ attribute (most plain python objects) which is
       equivalent to passing the __dict__ directly.
    If no header is given then either all or none of the rows must be sequences
    to ensure the correct order. If there are no sequences then the header will be
    derived from the keys of the mappings.

    >>> print(pretty_table([['a', 'hello', 'c', 1], ['world', 'b', 'd', 2]]))
    a     | hello | c | 1
    world | b     | d | 2
    >>> print(pretty_table([['a', 'hello', 'c', 1], ['world', 'b', 'd', 2]], header='col1 col2 col3 col4'))
    col1  | col2  | col3 | col4
    ---------------------------
    a     | hello | c    | 1
    world | b     | d    | 2
    >>> print(pretty_table([{'a': 1, 'b': 2}, {'a': 3, 'b': 4}]))
    a | b
    -----
    1 | 2
    3 | 4
    >>> class C(object):
    ...     def __init__(self, a, b):
    ...         self.a = a
    ...         self.b = b
    ...
    >>> print(pretty_table([{'a': 1, 'b': 2}, C(3, 4), [5, 6]], header=['b', 'a']))
    b | a
    -----
    2 | 1
    4 | 3
    5 | 6
    >>> print(pretty_table([{'a': 1, 'b': 2}, C(3, 4), [5, 6]]))
    Traceback (most recent call last):
    ...
    ValueError: Cannot mix sequences and other types of rows without specifying a header
    >>> print(pretty_table([[1, 2], [3, 4, 5]]))
    Traceback (most recent call last):
    ...
    ValueError: Mismatched lengths.
    First row (len = 2):
    [1, 2]
    Current row (len = 3):
    [3, 4, 5]
    >>> print(pretty_table([{'a': 1, 'b': 2}], header='c d'))
    Traceback (most recent call last):
    ....
    KeyError: "Tried to access 'c', only keys are: ['a', 'b']"
    """
    rows2 = []
    if header:
        header = ensure_list_if_string(header)
        rows2.insert(0, header)
        row_type = ['any']
    else:
        header = []
        row_type = [None]

    def require_type(t):
        if row_type[0] not in (None, t, 'any'):
            raise ValueError('Cannot mix sequences and other types of rows without specifying a header')
        if row_type[0] is None:
            row_type[0] = t

    def handle_dict(d):
        require_type('mapping')
        if not header:
            header[:] = sorted(d.keys())
            rows2.insert(0, header)
        return [helpful_error_dict_get(d, key) for key in header]

    for row in rows:
        if isinstance(row, Mapping):
            row = handle_dict(row)
        elif isinstance(row, Sequence):
            require_type('sequence')
            if rows2 and len(row) != len(rows2[0]):
                raise ValueError('Mismatched lengths.\n'
                                 'First row (len = %s):\n%s\n'
                                 'Current row (len = %s):\n%s' %
                                 (len(rows2[0]), rows2[0], len(row), row))
        else:
            row = handle_dict(row.__dict__)
        rows2.append(row)

    rows = [[str(cell) for cell in row] for row in rows2]
    widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]
    lines = [' | '.join(cell.ljust(width) for cell, width in zip(row, widths)).strip()
             for row in rows]
    if header:
        lines.insert(1, '-' * len(lines[0]))
    return '\n'.join(lines)


def date_to_datetime(d):
    """
    >>> date_to_datetime(date(2000, 1, 2))
    datetime.datetime(2000, 1, 2, 0, 0)
    >>> date_to_datetime(datetime(2000, 1, 2, 3, 4, 5))
    datetime.datetime(2000, 1, 2, 3, 4, 5)
    """
    if not isinstance(d, datetime):
        d = datetime.combine(d, datetime.min.time())
    return d


class DecentJSONEncoder(JSONEncoder):
    """
    >>> json.dumps([UserList(), (x for x in range(3)), HelpfulErrorDict(),
    ... Decimal('0.123'), Fraction(1, 3),
    ... date(2001, 2, 3), datetime(2004, 5, 6, 7, 8, 9), time(10, 11, 12)],
    ... cls=DecentJSONEncoder)
    '[[], [0, 1, 2], {}, 0.123, 0.3333333333333333, "2001-02-03T00:00:00", "2004-05-06T07:08:09", "10:11:12"]'
    >>> from itertools import repeat
    >>> json.dumps(repeat(5), cls=DecentJSONEncoder)
    Traceback (most recent call last):
    ...
    ValueError: Object of type repeat has more than 10000 elements.
    >>> len(json.dumps(repeat(5, times=20000), cls=DecentJSONEncoder, max_iterable_elements=50000))
    60000
    """

    def __init__(self, *args, **kwargs):
        self.max_iterable_elements = kwargs.pop('max_iterable_elements', 10000)
        super(DecentJSONEncoder, self).__init__(*args, **kwargs)

    def default(self, o):
        if isinstance(o, Sequence):
            if isinstance(o, (basestring, list, tuple)):
                return o
            return tuple(o)
        if isinstance(o, Mapping):
            return dict(o)
        if isinstance(o, (Decimal, Rational)):
            return float(o)
        if isinstance(o, date):
            return date_to_datetime(o).isoformat()
        if isinstance(o, time):
            return o.isoformat()
        try:
            iterable = iter(o)
        except TypeError:
            pass
        else:
            result = list(islice(iterable, self.max_iterable_elements + 1))
            if len(result) > self.max_iterable_elements:
                raise ValueError('Object of type %s has more than %s elements.' %
                                 (o.__class__.__name__, self.max_iterable_elements))
            return result
        # Let the base class default method raise the TypeError
        return JSONEncoder.default(self, o)


if __name__ == "__main__":
    import doctest

    doctest.testmod()