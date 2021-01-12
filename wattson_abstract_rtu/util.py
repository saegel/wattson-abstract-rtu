from typing import Union
COA = Union[int, str]
IOA = Union[int, str]

control_direction_processinfo_type_ids = range(45,70)

def check_pkg(name):
    from pip._internal.utils.misc import get_installed_distributions
    pkg_names = [pkg.project_name for pkg in get_installed_distributions()]
    return name in pkg_names

FCS_installed = check_pkg("FCS")

# key = ASDU type ID; value = permitted IO values set to/ returned
type_id_to_permitted_IOs  = {
    1: (0, 1),
    2: (0, 1),
    30: (0, 1),
    45: (0, 1),
    58: (0, 1),
    3: (0, 1, 2, 3),
    4: (0, 1, 2, 3),
    31: (0, 1, 2, 3),
    46: (0, 1, 2, 3),
    59: (0, 1, 2, 3),
    11: range(-32768, 3278),
    12: range(-32768, 3278),
    49: range(-32768, 3278),
    62: range(-32768, 3278)
}

class sink_logger():
    def __str__(self):
        return "This is not a real logger but only a sink"

    def warning(self, msg):
        return

    def critical(self, msg):
        return

    def info(self, msg):
        return

    def debug(self, msg):
        return

    def error(self, msg):
        return

def insert_relationships(datapoints):
    """Inserts an empty relationship at index 4"""
    new_datapoints = set()
    for dp in datapoints:
        cast_dp = list(dp)
        cast_dp.insert(4, "")
        new_datapoints.add(tuple(cast_dp))
    return new_datapoints

