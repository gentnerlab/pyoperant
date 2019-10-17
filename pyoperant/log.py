from logging import RootLogger

class PyoperantLogger(RootLogger):
    """ Logs pyoperant events
    """
    def info(self, msg, *args, **kwargs):
        super().info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        super().warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        super().error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        super().critical(msg, *args, **kwargs)

    def log(self, msg, *args, **kwargs):
        super().log(msg, *args, **kwargs)
