from django.utils.deprecation import MiddlewareMixin
from django_statsd.middleware import (
    GraphiteMiddleware,
    GraphiteRequestTimingMiddleware,
)


# Update django_statsd middleware to newer Django requirements
class GraphiteMiddleware(MiddlewareMixin, GraphiteMiddleware):
    pass


class GraphiteRequestTimingMiddleware(
        MiddlewareMixin, GraphiteRequestTimingMiddleware):
    pass


# We need access to request metadata from within patched support code. Store
# the request in a thread global
def global_request_middleware(get_response):
    from .global_request import ThreadLocalRequest

    def middleware(request):
        with ThreadLocalRequest(request):
            return get_response(request)

    return middleware


# Record memory and CPU stats per view
def memory_cpu_stats_middleware(get_response):
    import time
    import psutil

    from collections import Counter
    from django_statsd.clients import statsd
    from .global_request import get_view_name

    mem_entries = (
        'rss',
        'shared_clean', 'shared_dirty',
        'private_clean', 'private_dirty'
    )

    def summed(info):
        res = dict.fromkeys(mem_entries, 0)
        for path_info in info:
            for name in mem_entries:
                res[name] += getattr(path_info, name)
        return res

    def middleware(request):
        cpu_before = time.clock_gettime(time.CLOCK_PROCESS_CPUTIME_ID)
        mem_before = summed(psutil.Process().memory_maps())
        try:
            return get_response(request)
        finally:
            cpu_after = time.clock_gettime(time.CLOCK_PROCESS_CPUTIME_ID)
            statsd.gauge(
                'cpu.{}'.format(get_view_name()),
                cpu_after - cpu_before)
            mem_after = summed(psutil.Process().memory_maps())
            mem_key_base = 'memory.{}.{{}}'.format(get_view_name())
            for name, after in mem_after.items():
                diff = after - mem_before[name]
                statsd.gauge(mem_key_base.format(name) + '.total', after)
                statsd.gauge(mem_key_base.format(name) + '.change', diff)

    return middleware
