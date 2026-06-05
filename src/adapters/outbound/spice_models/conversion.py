"""
Back-compat re-export shim.

Канонические реализации переехали в `domain/spice_pwrs.py` (T030 —
чтобы application use case `run_spice_import` мог использовать без
adapter→adapter layer violation). Existing imports из этого модуля
продолжают работать.
"""

from __future__ import annotations

from domain.spice_pwrs import convert_ayumi_to_ngspice, convert_pwrs_to_ngspice

__all__ = ['convert_ayumi_to_ngspice', 'convert_pwrs_to_ngspice']
