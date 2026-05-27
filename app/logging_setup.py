import logging

class InMemoryHandler(logging.Handler):
    def __init__(self, capacity=1000):
        super().__init__()
        self.capacity = capacity
        self.logs = []

    def emit(self, record):
        log_entry = self.format(record)
        self.logs.append(log_entry)

        # Ограничиваем размер (чтобы память не росла бесконечно)
        if len(self.logs) > self.capacity:
            self.logs.pop(0)


# create handler
memory_handler = InMemoryHandler(capacity=1000)

formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(message)s"
)
memory_handler.setFormatter(formatter)

# set root logger
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

# don't add if exists
if not logger.handlers:
    logger.addHandler(memory_handler)
