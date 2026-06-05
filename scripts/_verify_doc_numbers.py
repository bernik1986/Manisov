import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.main import _augment_template_context

ctx = {
    "certificates": [
        {"certificate_type": "COP Ship's Cook", "certificate_code": "COP_COOK", "certificate_number": None},
        {"certificate_type": "Radar Observer", "certificate_code": "RADAR", "certificate_number": "1429668"},
        {"certificate_type": "COC GMDSS", "certificate_code": "COC_GMDSS", "certificate_number": "COC GMDSS"},
    ],
    "diplomas": [],
    "documents": [],
}
_augment_template_context(ctx)
checks = [
    "radar_document_number",
    "gmdss_document_number",
    "coc_gmdss_certificate_number",
    "cop_ships_cook_document_number",
]
for key in checks:
    print(key, repr(ctx.get(key)))
