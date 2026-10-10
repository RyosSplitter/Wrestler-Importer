"""Persist size-fitting evidence, including jobs that cannot safely export.

Sizes describe stored PAC sections, not expanded runtime memory requirements.
This module does not compress, reduce or publish a model.
"""
import json
from pathlib import Path

from tools.pac_inspect import inspect_pac


class SizeFitReport:
    def __init__(self, path, maximum, inputs, source):
        self.path = Path(path)
        self.data = dict(status='in_progress', maximum_pac_bytes=maximum,
                         effective_aligned_maximum_bytes=maximum // 2048 * 2048,
                         inputs=inputs, source=source, attempts=[])
        self._save()

    def _save(self):
        temporary = self.path.with_suffix('.tmp')
        temporary.write_text(json.dumps(self.data, indent=2, allow_nan=False)+'\n',
                             encoding='utf-8')
        temporary.replace(self.path)

    def record(self, candidate, *, accessory_sections=(), **details):
        report = inspect_pac(candidate)
        sizes = {s['id']: s['size'] for s in report['sections']}
        components = dict(model_stored_bytes=sizes[2],
                          textures_stored_bytes=sizes[9],
                          accessory_models_stored_bytes=sum(sizes[i] for i in accessory_sections),
                          retained_base_stored_bytes=sum(n for i,n in sizes.items() if i not in {2,9,*accessory_sections}),
                          headers_and_padding_bytes=len(candidate)-sum(sizes.values()))
        row = dict(details, pac_bytes=len(candidate), **components)
        self.data['attempts'].append(row)
        self.data['smallest_attempt'] = min(self.data['attempts'], key=lambda a:a['pac_bytes'])
        self._save()
        return row

    def finish(self, fitted):
        self.data['status'] = 'size_fitted_pending_validation' if fitted else 'budget_exceeded'
        smallest = self.data['smallest_attempt']
        self.data['over_budget_bytes'] = max(0, smallest['pac_bytes']-self.data['maximum_pac_bytes'])
        self.data['over_aligned_budget_bytes'] = max(0, smallest['pac_bytes']-self.data['effective_aligned_maximum_bytes'])
        self._save()

    def error(self):
        row = self.data['smallest_attempt']
        return ValueError(
            f"Smallest candidate is {row['pac_bytes']:,} bytes, "
            f"{self.data['over_budget_bytes']:,} over the "
            f"{self.data['maximum_pac_bytes']:,}-byte budget. "
            f"Stored model: {row['model_stored_bytes']:,} bytes; "
            f"textures: {row['textures_stored_bytes']:,}; "
            f"accessory models: {row['accessory_models_stored_bytes']:,}; "
            f"retained base data: {row['retained_base_stored_bytes']:,}; "
            f"headers/padding: {row['headers_and_padding_bytes']:,}. "
            'Export withheld; protected anatomy was not reduced to force a fit. '
            f'Size-fitting details: {self.path}'
        )
