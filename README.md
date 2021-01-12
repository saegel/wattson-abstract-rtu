# Wattson Abstract RTU
This module provides a standardized interface for software-based RTU 
implementations for interacting with different type of Power Grid Backends. 
These backends either can be physical components, local software implementations,
or distributed Power Simulations for representing complex grids.

**This module does not provide any simulative functionalities but serves the 
sole purpose of enabling exchangable RTU implementations and Power Grid Backends.**

# RTU Abstraction Layer

This document specifies the functionality provided by the RTU abstraction layer, implemented as RTUBackend interface.
The main communication with datapoints attached to the RTU should be handled through this interface.
Since both the simulation and RTU model will change how a RTU can and should be interacted with, some functions need to be implemented
by the inheriting class.
In the current design, it is expected that a class inheriting from the RTU backend implements *all* functionality specific
to a combination of simulation and RTU model.
We expect a specific RTU model to define a new RTU backend class that inherits from our interface and sets it as attribute of the main RTU object.

## Datapoints:
A RTU is initialised with information about all datapoints attached to it.
Only changing the default cause of transmission for a datapoint is possible at a later point.
The format of datapoints handed over may vary, we require:
- The datapoint is castable to a tuple
- The first four entires accessible as [0:5] represent [coa, ioa, type-ID, cot, related-ioa] (Information Object Adddress, Common Address, 
    default ASDU-Type-ID, default Cause of Transmission, ioa of related datapoint then identified as (coa, related-ioa))
- coa, ioa, related-ioa types: `int` or `str`; their values are stored, retrieved, and compared against in a type-sensitive fashion!
- type-ID, cot type: `int`; cot in `[1,47]`; type-ID roughly in `[1,127]` (some values of the interval are undefined)
- the default cot will be chosen when a query is send and no new cot is given
- If `cot == 1`, the interface assumes periodic updates are send to the RTU as mentioned in IEC-104
- the [coa, ioa, type-ID, cot, related-ioa] combination is referred to **primitive datapoint**,
    its entire model-specific combination as **complex datapoint**
- any usage of the cot in the following is assumed to conform with IEC-104

If additional information, like Panda-DataFrame references, are necessary in your model, hand them
    over in all entries after the fifth.


## Model-Specific Adoptions:
Retrieving values from/ writing values to datapoints and any further communication is model-dependent
and requires two functions to be implemented.
The types `COA` and `IOA` are set to `Union[int, str]`.

1. `_build_IO_query(self, coa: COA, ioa: IOA, cot: int = 0, value=None)`
    - construct an IO query in your model-specific format.
    - behaviour for coa-ioa combinations not referring to a datapoint attached the RTU is undefined
    - if `cot==0`, chooses the cot the backend was initialised with
    - if `value is None`, builds a get-query, otherwise a set-query
        - Resulting limitation: cannot set an IO to `None` 
2. `_send_query(self, query: Any)`
    - sends the IO query based on your RTU-grid-simulation-model
    - return `None` if some error occured. `non-None`  return may either signal correctly sent set-query or return value from get-query.
    - The respective return value is forwarded when retrieving/ setting IOs.


Neither of these functions is expected to be called directly by an operator.


## Pre-Defined Functionality:
### Functions
The RTU backend pre-defines these functions:


1. `__init__(self, coa: COA, datapoints: Iterable[Tuple[COA, IOA, int, int, ...]], autostart=False,
             logger=None, includes_relationship=False)`
    - sets up datapoint storage
    - the datapoints need to be deterministcally castable to tuples in the datapoints section
    - coordination with other devices etc. can be started with `autostart=True` that calls function 2
    - inserts an empty-relationship after index [3] if `includes_relationship=False`
        - if `includes_relationship=True`, expects the value at [4] to be of type IOA and the
            same primitive datatype used for the ioas at the 2nd tuple-index
    - checks all relationships on correctness (see function 3)
    - raises `RuntimeError` if an invalid relationship is stored (see function 3)
    - ends by executing function 2 if `austostart=True`

2. `wait_until_ready(self, timeout: Union[float, None]=None) -> None`
    - terminates as soon as all model-dependent coordinations \& start functions are completed
    - raises a `TimeoutError` if your model-dependent setups have not finished in
        the given timeout
    - `timeout` in `[s]` for numbers, never forces stop if `timeout is None` 
    - may requires overwriting to conform with your RTU + simulator model

3.  `sanitise_check_relationships(self) -> bool`:
    - checks if all datapoints storing a relationship link to an attached datapoint
        with the same coa and stored relation-ship.
    - raises a `RuntimeError` if an invalid relationship is found
        
4.  `_invalid_type_id(self, coa: COA, ioa: IOA, type_id: int) -> Union[bool, None, int]`
     - checks if the type_id-argument and the datapoint's default type_id are command-query type_ids (in [45,69])
     - if True, returns `defaulttype_id == type_id` 
     - reasoning: restrict allowed command-queries to those specified by the datapoint
     - returns `None` for unattached datapoint
     - returns `0` if either the handed over type_id or the type_id stored for the datapoint
        are not command-query-type_ids 
        
5. `get_IO(self, coa: COA, ioa: IOA, cot: int=0, type_id: int=0) -> Any`
    - retrieve the IO based on the coa-ioa combination
    - returns `None` if the RTU has no such datapoint with a resp. IO attached to it or
        a type_id != 0 is given and which is invalid for this datapoint
    - if `cot==0`, chooses default cot stored

6. `has_IO(self, coa: COA, ioa: IOA) -> bool`
    - check if an IO with the given coa-ioa combination is attached to the RTU

7. `set_IO(self, coa: COA, ioa: IOA, value, cot: int=0, type_id: int=0) -> Union[bool, None]`
    - sets an IO on a datapoint
    - if `cot==0` build query with default cot
    - returns the model-dependent query response for attached datapoints and
        `None` if the RTU does not know such an IO or type_id is given which is not valid for this datapoint
         - resulting limitation: cannot differentiate between the return of a `None` query response and a 
            non-attached IO

8. `get_related_IO(self, coa: COA, ioa: IOA, cot: int = 0) -> Any`
    - performs`get_IO` but for the datapoint related to the (coa, ioa)-identified datapoint
    - also returns `None` if no relationship is stored

9. `set_related_IO(self, coa: COA, ioa: IOA, value, cot: int = 0) -> Union[bool, None]`
    - performs `set_IO` but for the datapoint related to the (coa, ioa)-identified datapoint
    - also returns `None` if no relationship is stored
    
10. `get_periodic_ids(self) -> Set[Tuple[COA, IOA]]`
    - returns all coa-ioa combinations the RTU expects periodic messages from (initialised with `cot==1`)

11. `get_periodic_data_points(self) -> Set[Tuple[COA, IOA, int, int]]`
    - returns all primitive datapoints the RTU expects periodic messages from
  
12.  `get_periodic_ioas(self, coa: COA = -1) -> Set[IOA]`
    - returns all IOAs of periodicly updating datapoints with the given coa
    - if `coa==-1`, checks for all datapoints with the backend's coa

13. `get_data_point(self, coa: COA, ioa: IOA, with_value=False) -> Union[None, Tuple, Tuple[Tuple, Any]]`
    - retrieves the primitive datapoint corresponding to the coa-ioa combination
    - returns `None` if no such datapoint is known
    - adds the resp. IO if `with_value=True` 

14. `get_related_data_point(self, coa: COA, ioa: IOA, with_value=False) -> Union[None, Tuple, Tuple[Tuple, Any]]`
    - performs `get_data_point` but on the related datapoint instead
    - also returns `None` if no relationship is stored

15. `change_cause_of_transmission(self, coa: COA, ioa: IOA, new_cot: int) -> None`
    -  change the default-cot for a datapoint attached
    - if `new_cot== 1 or default_cot==1` expects that a model-dependent command to the datapoint is send
        to update the periodic-update status
    - does not change if `cot not in [1,47]`
            
16. `get_ioas(self, coa: COA = -1) -> Set[IOA]`
    - retrieve all ioas from datapoints with the given coa attached to the RTU
    - if `coa==-1`, checks for the backend's coa

17. `get_data_points(self) -> Set(Tuple[COA, IOA, int, int])`
    - retrieves all primitive data points attached to the RTU

18. `_get_complex_data_point(self, coa: COA, ioa: IOA, with_value=False) -> Union[None, Tuple, Tuple[Tuple, Any]]`
    - retrieves the respective complex data point 
    - also returns the IO if `with_value=True`

19. `_get_complex_related_data_point(self, coa: COA, ioa: IOA, with_value=False) -> Union[None, Tuple, Tuple[Tuple, Any]]`
    - performs `_get_complex_data_point` on the related datapoint
    - also returns `None` if no relationship is stored

The initialisation function should be overwritten if more objects/ data for the communication between RTU and simulation model needs to be provided
to send or build queries.
For instance, Julian Filter's pandapower model also simulates the communication with ZMQ.
Corresponding wrappers and other metadata necessary to partially access, initialise and control the 
    client would thus be necessary to be added by the inheriting backend.
This may require overwriting `wait_until_ready(...)` as well.

### Attributes
The following attributes are defined upon initialisaton of the interface
1. `data_store`: `Dict[COA, Dict[IOA, Tuple[COA, IOA, int, int, IOA, ...]]]`
    - stores all complex datapoints for building the queries etc.
    - this format to ensure easy traversal and compability with all known models
2. `datapoints`: `Set[Tuple[COA, IOA, int, int, IOA]]`
    - stores all primitive datapoints
3. `coa`: `COA`
    - coa of the RTU
4. `started`: `threading.Event`
    - marks start-up \& initialisation of all model-dependent clients etc.
5. `logger`: `Union[sink_logger, logging.Logger]`
    - logger to use if wanted
    - if no logger is handed over, a sink_logger that discards all messages is set-up,
        this cleans up logging behaviour as no checkup if a logger exists is necessary
    - the `sink_logger` only provides the main logging functions:
        - `.critical(msg), .error(msg), .warning(msg), .info(msg), .debug(msg)`
6. `__inserted_relationship`: `Bool`
    - marks whether insertion of empty relationships were necessary
    - mostly aimed at debugging

### Properties (read-only)
1. `logging`: If a non-sink logger is attached

### Logging
Logging is assumed to be done through the `logging` package.
The interface assumes the logger is already set up in regards to file handlers, etc. .
The logger is assumed to be separate for each RTU or as it does not always repeat the backend's
    COA.
A sink is connected that accepts all main logging messages stated above if no real logger is
    handed over.
The interface logs the following data:
1. `CRITICAL`
    - the backend could not start clients etc. in `wait_until_ready` in the time-threshold given
2. `WARNING`
    - calling `set_IO` or `get_IO` on an unattached datapoint 
    - executing `get_related_IO` or `set_related_IO` on a datapoint without a relationship
    - sending the query for `set_IO`, `get_IO`, or or its related-datapoint versions on an attached datapoint failed for some other 
        reason
    - changing the cot for an unattached datapoint or trying to set it to an invalid value
    - trying to set/get IOs with an invalid type_id for the given datapoint or if the corresponding
        IO does not lie in the IEC104-range for this type_id
3. `INFO`
    - whenever the `self.started` status changes
    - time [s] it took to setup a client (if applicable)
    - whenever the periodicity of a datapoint was changed
4. `DEBUG`
    - `str(query)` send and its result



## Recommended Implementations:
A model often needs to be constructable from exported data, e.g., pickle, yaml, or regular xml files.
This is not strictly necessary, but encouraged and should be implemented through a static `from_data(...)` function.

1. `stop(self) -> bool`
    - stops all model-specific communicators (zmq-clients, etc.)
    - returns success of this operation (should only fail in special cases or raise 
         exceptions instead)
    - clears the started Event

2. `__del__(self)`
    - stops all model-specific communicators (zmq-clients, etc.) safely

### Testing
We encourage tests written with `pytest`.
For several only indirectly or model-independent functions already fully defined by the backend,
test-functions can be imported from `RTU/tests/RTUs.py`, denoted by a `standard` prefix.
They only require the RTU or Backend + the datapoints initialised with as input.
Example tests for a constant and pandapower-backend are defined there as well.


### A note about pandapower 
To our knowledge, many implementations use pandapower, panda DataFrames, and PPQueries in one way or another.
There exist some test examples and corresponding Backend that use the following DataFrame input format:
- `[coa, ioa, type-ID, cot, pp_table, pp_column, pp_index, others]`
    - this does not include relationship-ioas and requires initialising 
        the backend with `includes_relationship=False`!

and the following PPQuery format as named tuple:
- `[table, column, index, value]`

If you make your data frame fit to this format, you should be able to copy the  `_build_IO_query` implementation from the `PandapowerBackend` example.



## Model-Compability:
The interface requires a python version `>=3.5`.
Some examples will require a higher python version due to other dependencies. If this is the case, it is clearly marked.

Examples are listed in the `RTU/Backends.py` file.
A mini-RTU-simulation with a Backend is given in `RTU/examples/RTUs.py`.


Please let us know if any of the following specifications do *not* hold. 

- the coa, ioa, relationship-ioas are not stored as integers/ strings; the cot/type-ID is not stored as integer in your model

- you believe other functionality is shared between the *vast* majority of RTU or simulation models and if implemented in this interface
    does not get in the way of those models the functionality is not shared with
- any other compability problem if this interface would be implemented for your RTU and simulation model

Or if the following any of these three *do* hold:
- your model requires the type-ID during IO-query construction/ sending
- your model allows IOs with a **valid** `None` value
    - since the send-query functions etc. return `None` for various errors
- a datapoint identified through (coa, ioa) needs to store a relationship to a datapoint with a different
    coa
