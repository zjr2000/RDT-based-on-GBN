import time


class Timer(object):
    def __init__(self, time_limit):
        self.start_time = -1
        self.time_limit = time_limit
        self.is_started = False

    def started(self):
        return self.is_started

    def is_time_out(self):
        if not self.started:
            return False
        return time.time() - self.start_time > self.time_limit

    def start_timer(self):
        self.is_started = True
        self.start_time = time.time()

    def stop_timer(self):
        self.is_started = False
