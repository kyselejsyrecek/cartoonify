import os
import logging

# Limit the number of largest memory allocations in output statistics.
# Set to 0 to print all memory allocations.
max_statistics = 0

if os.environ.get("PROFILING") is not None:
    profiling = True
    import tracemalloc
    tracemalloc.start()
else:
    profiling = False

def evaluation_point(snapshot_name):
    if profiling:
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics('lineno')
        length = len(stats) if max_statistics == 0 else max_statistics
        logging.debug("Profiling evaluation ({}):".format(snapshot_name))
        for stat in stats[:length]:
            logging.debug(stat)