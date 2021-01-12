import abc
from typing import Union, Tuple, Any, Iterable, Set, Optional, Callable
from threading import Event

from .util import COA, IOA, control_direction_processinfo_type_ids, type_id_to_permitted_IOs, \
    sink_logger


class BackendInterface(abc.ABC):
    """
    Defines the fundamental requirements, operator interactivity, and datapoint handling
        for a (virtualised) RTU as its backend.
    The inheriting backend implements some of the model-specific communication and all
        metadata needed to interact with IOs/datapoints.
    The actual RTU-object should only know the basic [coa, ioa, type-ID, cot]-quadruple for each
        datapoint. (Called 'primitive datapoint' here)
    For more information, see the specification.md file and examples.
    """

    def __init__(self,
                 coa: COA,
                 datapoints: Iterable[Tuple[COA, IOA, int, int, Any]],
                 autostart: bool = False,
                 logger=None,
                 includes_relationships: bool = False,
                 callback: Optional[Callable[[COA, IOA], Any]] = None):
        """
        Initialises datastorage and may start all model-specific simulations.
        Should be called by all inheriting classes.
        If it is overwritten and autostart enabled, all attributes required for the autostart
            already need to be defined before calling the super-init.
        :param coa: COA of the RTU
        :param datapoints: complete datapoints attached to the RTU, unchangeable;
                            each datapoint is deterministcally castable to a tuple
        :param autostart: if RTU-specific simulations and anything that may need to be waited for
                            should be started already
        :param logger: pre-initialised logger to use
        :param includes_relationships: if the datapoints include relationships to one another
            at the [4] index. If False, an empty relationship is inserted at the
                [4] index of the datapoint.
        :param callback: A Callable that is called as soon as a value is pushed from the Backend
            towards the RTU. Not all Backends need to implement this.
        """
        # one datapoint handed over = [coa, ioa, type-ID, cot, (relationship-IOA optional), use-case-data]
        # relationship-IOA forced as "" after initialisation if `includes_relationship` = False
        # a related datapoint is then identified by [coa, relationship-IOA]
        # if relationship-IOA != ""
        self.coa = coa
        self.data_store = {}
        self.datapoints = set()
        self.callback = callback

        # throws away all msgs but cleans up code because there is no need to always check for
        # the existence of a logger
        logger = sink_logger() if logger is None else logger
        self.logger = logger

        # for debugging
        self.__inserted_relationship = not includes_relationships
        if self.__inserted_relationship:
            self.logger.info("init data did not provide relationships - inserting empty datapoint relationships")

        for dp in datapoints:
            if not includes_relationships:
                dp = list(dp)
                dp.insert(4, "")
            dp = tuple(dp)

            if dp[0] not in self.data_store:
                self.data_store[dp[0]] = {dp[1]: dp}
            else:
                # expects unique coa-ioa combinations
                self.data_store[dp[0]][dp[1]] = dp
            self.datapoints.add(dp[0:5])

        if not self.sanitise_check_relationships():
            self.logger.critical("Stopping due to invalid relationship in datapoints. ")
            raise RuntimeError(f"Cannot initialise RTU-Backend with COA {self.coa}"
                               f" Some datapoint has an invalid relationship.")

        self.started = Event()

        if autostart:
            self.wait_until_ready()

    def get_IO(self, coa: COA, ioa: IOA, cot: int = 0, type_id: int = 0):
        """
        Retrieves the IO from an attached datapoint.
        :param coa: The COA for the requested Information Object
        :param ioa: The IOA for the requested Information Object
        :param cot: 0 -> choose default value initialised with
        :param type_id: != 0 -> check if returned IO is equal to allowed IOs for this ASDU type_id
        :return: None if the datapoint is not attached or the type_id doesn't match the expected
            for a datapoint, otherwise query result
        """
        if not self.has_IO(coa, ioa):
            self.logger.warning(f"tried to get IO for unattached datapoint with ioa {ioa} and coa {coa}")
            return None

        if not self._valid_type_id(coa, ioa, type_id):
            stored_type_id = self.get_data_point(coa, ioa)[2]
            self.logger.warning(f"Tried sending a get-IO query with invalid command-query-ID "
                                f"{type_id} to dp with (coa, ioa) ({coa}, {ioa})."
                                f" Expecting type_id {stored_type_id} for command-queries to this dp."
                                f" Not sending this query.")
            return None

        query = self._build_IO_query(coa, ioa, cot)

        res = self._send_query(query)
        if res is None:
            self.logger.warning(f"Retrieving IO for attached datapoint with (coa, ioa, cot) "
                                 f"({coa}, {ioa}, {cot}) failed!")
        elif type_id in type_id_to_permitted_IOs \
                and res not in type_id_to_permitted_IOs[type_id]:
            # default type_id 0 not allowed for ASDUs -> never in type_ID_to...

            self.logger.warning(f"Retrieved IO with invalid value {res} "
                                    f"for type_id {type_id} from dp with (coa, ioa) ({coa}, {ioa})."
                                    f"Expecting value in {type_id_to_permitted_IOs[type_id]}.")
        else:
            self.logger.debug(f"Send query {query} to datapoint with (coa, ioa, cot): "
                              f"({coa}, {ioa}, {cot}) and result {res}")
        return res

    def has_IO(self, coa: COA, ioa: IOA) -> bool:
        return coa in self.data_store and ioa in self.data_store[coa]

    def set_IO(self, coa: COA, ioa: IOA, value, cot: int=0, type_id: int=0) -> Union[bool, None]:
        """
        Overwrites IO on an attached datapoint.
        :param coa: The COA for the Information Object to be set
        :param ioa: The IOA for the Information Object to be set
        :param cot: if 0, send query with cot this datapoint was initialised with
        :param type_id: if != 0 & command-query-type_id, check if this type_id is allowed
                fot this dp.
        :return: None if datapoint identified by coa-ioa is not attached to this RTU
                or the type_id is not allowed for this datapoint,
                True/False depending on success of sending the query.
        Allows, but logs warning if an dp is set to a value invalid for this type_id
        """

        if not self.has_IO(coa, ioa):
            self.logger.warning(f"tried to set IO for unattached datapoint with (coa, ioa)"
                                f" ({ioa}, {coa})")
            return None
        stored_cot = self.get_data_point(coa, ioa)[3]
        if cot == 0:
            cot = stored_cot
        if not self._valid_type_id(coa, ioa, type_id):
            stored_type_id = self.get_data_point(coa, ioa)[2]
            self.logger.warning(f"Tried to send a set-IO query with invalid command-query-type_id "
                                f"{type_id} to dp with (coa, ioa) ({coa}, {ioa})."
                                f"Expecting type_id {stored_type_id} for command-queries to this dp."
                                f"Not sending the query.")
            # only allow queries if they have the type_id dp allows just this command
            return None

        if type_id in type_id_to_permitted_IOs \
                and value not in type_id_to_permitted_IOs[type_id]:
            self.logger.warning(f"Sending a set-IO query to with invalid value {value} "
                                f"for type_id {type_id} to dp with (coa, ioa) ({coa}, {ioa})."
                                f"Expecting value in {type_id_to_permitted_IOs[type_id]}.")

        query = self._build_IO_query(coa, ioa, cot, value)
        res = self._send_query(query)

        self.logger.debug(f"send query {query} to datapoint with (coa, ioa, cot): "
                           f"({coa}, {ioa}, {cot}) and result {res}")
        if res is None:
            self.logger.warning(f"setting IO for attached datapoint with (coa, ioa, cot) "
                             f"({coa}, {ioa}, {cot}) failed!")
        return res

    def set_related_IO(self, coa: COA, ioa: IOA, cot: int=0, type_id: int=0) -> Union[bool, None]:
        """Sets the IO related to the coa-ioa identified datapoint."""
        if not self.has_IO(coa, ioa):
            self.logger.warning(f"cannot set related IO from non-attached dp with (coa, ioa)"
                                f"({coa}, {ioa})")
        # relationships were sanitised before; related dp has to be attached
        related_dp = self.get_related_data_point(coa, ioa)
        return self.set_IO(related_dp[0], related_dp[1], cot, type_id)

    def get_related_IO(self, coa: COA, ioa: IOA, cot: int=0, type_id: int=0) -> Union[bool, None]:
        """Gets the IO related to the coa-ioa identified datapoint."""
        if not self.has_IO(coa, ioa):
            self.logger.warning(f"cannot read related IO from non-attached dp with (coa, ioa)"
                                f"({coa}, {ioa})")
        # relationships were sanitised before; related dp has to be attached
        related_dp = self.get_related_data_point(coa, ioa)
        return self.get_IO(related_dp[0], related_dp[1], cot, type_id)

    def get_data_point(self, coa: COA, ioa: IOA, with_value=False) -> \
            Union[None, Tuple, Tuple[Tuple, Any]]:
        """
        Retrieves primitive datapoint, optionally with current IO.
        :param with_value: if IO should be returned as well
        :return: None if datapoint is not attached, primitive datapoint alone/ with IO otherwise
        """
        res = self._get_complex_data_point(coa, ioa, with_value)
        if res is None:
            # dp not attached to RTU
            return None
        elif len(res) == 2:
            # with_value
            return res[0][0:5], res[1]
        else:
            return res[0:5]

    def get_related_data_point(self, coa: COA, ioa: IOA, with_value=False) -> \
            Union[None, Tuple, Tuple[Tuple, Any]]:
        """
        Retrieves primitive datapoint related to the ID handed over, optionally with current IO.
        :param with_value: if IO should be returned as well
        :return: None if datapoint is not attached, primitive datapoint alone/ with IO otherwise
        """
        res = self._get_complex_related_data_point(coa, ioa, with_value)
        if res is None:
            return None
        elif len(res) == 2:
            # with_value
            return res[0][0:5], res[1]
        else:
            return res[0:5]

    def _get_complex_data_point(self, coa: COA, ioa: IOA, with_value=False) -> \
            Union[None, Tuple, Tuple[Tuple, Any]]:
        """
        Retrieves entire datapoint with all meta-information, optionally with IO.
        :param with_value: if IO should be returned as well
        :return: None if datapoint is not attached, complex datpoint alone/ with IO otherwise
        """
        if not self.has_IO(coa, ioa):
            return None

        dp = self.data_store[coa][ioa]
        if with_value:
            return dp, self.get_IO(coa, ioa, dp[3])
        return dp

    def _get_complex_related_data_point(self, coa: COA, ioa: IOA, with_value=False) -> \
            Union[None, Tuple, Tuple[Tuple, Any]]:
        dp = self._get_complex_data_point(coa, ioa)
        if dp is None:
            return None
        return self._get_complex_data_point(coa, dp[4], with_value)

    def get_ioas(self, coa: COA = -1) -> Set[IOA]:
        """
        Retrieves all IOAs for a given coa.
        In case no coa is specified, check those datapoints that have the same coa as the RTU.
        Is type-sensitive as of now.    TODO: Future patch?
        """
        coa = self.coa if coa == -1 else coa
        res = {dp[1] for dp in self.datapoints if dp[0] == coa}
        return res

    def get_periodic_ids(self) -> Set[Tuple[COA, IOA]]:
        """
        :return: all coa-ioa identifiers of all datapoints the RTU expects periodic updates from
        """
        res = {dp[0:2] for dp in self.datapoints if dp[3] == 1}
        # dp[3] = cot; cot == 1 -> periodic transmission reason
        return res

    def get_periodic_ioas(self, coa: COA = -1) -> Set[IOA]:
        """
        Retrieves all periodic IOAs for a given coa.
        In case no coa is specified, check those datapoints that have the same coa as the RTU.
        Is type-sensitive as of now.
        """
        coa = self.coa if coa == -1 else coa
        res = {dp[1] for dp in self.datapoints if dp[3] == 1 and dp[0] == coa}
        return res

    def get_periodic_data_points(self) -> Set[Tuple[COA, IOA, int, int, IOA]]:
        """
        :return: all primitive datapoints the RTU expects periodic updates from
        """
        # dp[3] = cot; cot == 1 -> periodic transmission reason
        return {dp for dp in self.datapoints if dp[3] == 1}
 
    def get_data_points(self) -> Set[Tuple[COA, IOA, int, int, IOA]]:
        """
        :return: all primitive datapoints attached
        """
        return self.datapoints

    def wait_until_ready(self, timeout: Union[float, None]=None) -> None:
        """
        Starts all model-specific communication, servers, etc. and waits until the simulation
        can be started.
        Needs to be overwritten if such waiting between devices exists in your model.
        :param timeout: seconds after which to stop waiting; if -1.0, never stop
        :return: if the RTU is ready
        """
        if not self.started.is_set():
            self.started.set()
        self.logger.info(f"all clients were successfully started")

    def change_cause_of_transmission(self, coa: COA, ioa: IOA, new_cot: int) -> None:
        """
        Change the default-cot expected for communication with a given datapoint.
        :param new_cot: int in [1,47]
        """
        dp = self._get_complex_data_point(coa, ioa)
        if dp is None:
            self.logger.warning(f"cannot change cot for unattached datapoint with (coa, ioa)"
                                f"({coa}, {ioa})")
            return
        elif new_cot not in range(1,48):
            self.logger.warning(f"tried to change cot to invalid value {new_cot} for datapoint with"
                                f"(coa, ioa) ({coa}, {ioa})")
            return
        prim_old_dp = dp[0:5]
        tmp = list(dp)
        tmp[3] = new_cot
        new_dp = tuple(tmp)
        self.data_store[coa][ioa] = new_dp
        self.datapoints.remove(prim_old_dp)
        self.datapoints.add(new_dp[0:5])

    def sanitise_check_relationships(self) -> bool:
        """
        :return: if relationships specified match IOAs
        """
        for dp in self.datapoints:
            if dp[4] and not self.has_IO(dp[0], dp[4]): # relationship = IOA of datapoint with same coa
                self.logger.critical(f"Invalid relationship for datapoint {dp}."
                                     f"No dp with Relationship-ID {dp[4]} found!")
                return False
        return True

    def _valid_type_id(self, coa: COA, ioa: IOA, type_id: int) -> Union[bool, None, int]:
        """
        :return:
            None: dp not attached to RTU
            0: type_id handed over or stored for the dp not a command-query-type_id (45-69)
            True: type_id and stored dp-type_id equal command-query-type_id
            False: type_id and stored dp-type_id unequal command-query-type_id
        if a command query with the given cot is allowed for this datapoint
        """
        dp = self.get_data_point(coa, ioa)
        if dp is None:
            return None
        if dp[2] in control_direction_processinfo_type_ids \
            and type_id in control_direction_processinfo_type_ids:
            return dp[2] == type_id
        return True


    @abc.abstractmethod
    def _build_IO_query(self, coa: COA, ioa: IOA, cot: int=0, value=None):
        """
        Constructs a model-specific get/set-IO-query for datapoint identified by the
            coa-ioa combination with given cause cot.
        If the datapoint is not attached to this RTU, the return value may be undefined.
        :param cot: cause-of-transmission for the query; cot == 0 -> chooses cot the datapoint
                    was initialised with.
        :param value: if None -> get query; else set IO to the respective value
        :return: query with all meta-info necessary to your model
        """

    @abc.abstractmethod
    def _send_query(self, query: Any):
        """
        Wrapper sending a query from _build_IO_query based on your (communication-)model.
        :param query: Query to send
        :return: IO for get-query; None if datapoint is not attached; else model-dependent
        """
        ...

    @property
    def logging(self):
        return not isinstance(self.logger, sink_logger)

    @staticmethod
    def from_data(*args, **kwargs):
        """
        Constructs the BackendInterface from some exported data.
        Optional to implement.
        """
        pass
