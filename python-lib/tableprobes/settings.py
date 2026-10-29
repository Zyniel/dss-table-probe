"""The settings of a probe, as the user fills them in the probe form (probe.json)."""
from dataclasses import dataclass
from typing import Any, Dict, Optional

# How the Oracle dictionary is read (setting "oracle_dictionary")
#   auto  DBA_ views; if the connection may not read them, the views of the login user
#   dba   DBA_ views only: SELECT_CATALOG_ROLE or SELECT ANY DICTIONARY
#   user  ALL_ views, and USER_SEGMENTS for the sizes: no grant needed, but only the sizes
#         of the tables of the login user can be read
ORACLE_DICTIONARY_CHOICES = ("auto", "dba", "user")

DEFAULT_STALE_PCT = 10.0


@dataclass
class ProbeSettings:
    """Settings of one probe.

    read_connection    DSS connection the dictionary is read through, None for the
                       dataset's own connection
    oracle_dictionary  "auto", "dba" or "user"
    stale_pct          statistics are stale beyond this % of rows changed (statistics probe)
    """

    read_connection: Optional[str]
    oracle_dictionary: str
    stale_pct: float


def read_settings(config: Dict[str, Any]) -> ProbeSettings:
    """The settings of a probe from its config (the dict DSS gives to probe.py)."""
    read_connection = config.get("read_connection")
    if not read_connection:
        read_connection = None

    oracle_dictionary = config.get("oracle_dictionary") or "auto"
    if oracle_dictionary not in ORACLE_DICTIONARY_CHOICES:
        raise ValueError("Oracle dictionary %r: expected one of %s"
                         % (oracle_dictionary, ", ".join(ORACLE_DICTIONARY_CHOICES)))

    stale_pct = config.get("stale_pct")
    if stale_pct is None or stale_pct == "":
        stale_pct = DEFAULT_STALE_PCT
    stale_pct = float(stale_pct)
    if stale_pct <= 0:
        raise ValueError("Stale statistics threshold must be above 0 %%, got %s" % stale_pct)

    return ProbeSettings(read_connection=read_connection,
                         oracle_dictionary=oracle_dictionary,
                         stale_pct=stale_pct)
