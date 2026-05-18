"""NgspiceSimulator adapter — subprocess + ASCII raw parser (T008)."""

from adapters.outbound.ngspice.raw_parser import (
    NgspiceRawParseError,
    parse_ngspice_raw,
)

__all__ = [
    'NgspiceRawParseError',
    'parse_ngspice_raw',
]
