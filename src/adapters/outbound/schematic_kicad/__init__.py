"""
schematic_kicad — programmatic генератор `.kicad_sch` (T100).

Реализует port `ports.outbound.schematic_writer.SchematicWriter` + fluent
фасад `Schematic` для построения схем в Python (RC-фильтры, выпрямители,
SE-amp на лампах T006). KiCad 10 формат, embedded lib_symbols — без
зависимости от глобальной KICAD_SYMBOL_DIR.
"""

from adapters.outbound.schematic_kicad.facade import Schematic
from adapters.outbound.schematic_kicad.writer import KicadSchematicWriter

__all__ = ['KicadSchematicWriter', 'Schematic']
