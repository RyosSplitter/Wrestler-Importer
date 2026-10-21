"""Bounded Wii reader contract, separate from PS2 and Xbox 360 layouts."""
from pathlib import Path
import hashlib
from tools.wwe13_wii_corpus import bundles,verified_source_bundle as source_bundle


def selected_index(entry_id,count):
    if not isinstance(entry_id,str) or (entry_id and (len(entry_id)!=2 or not entry_id.isascii() or not entry_id.isdecimal())):
        raise ValueError('Choose a two-digit Wii costume index.')
    index=int(entry_id or '00')
    if not 0<=index<count:raise ValueError('Wii costume is outside the discovered containers.')
    return index


class WiiAdapter:
    key='wwe13-wii'

    def catalogue(self,path):
        raw=Path(path).read_bytes();found=bundles(raw)
        return dict(entries=[dict(id=f'{i:02d}',offset=b['offset']) for i,b in enumerate(found)],selected_entry='00',
                    source_sha256=hashlib.sha256(raw).hexdigest())

    def inspect(self,path,preview_folder=None,entry_id=''):
        path=Path(path);raw=path.read_bytes();catalogue=self.catalogue(path)
        index=selected_index(entry_id,len(catalogue['entries']))
        model,images,decode=source_bundle(raw,index)
        result=dict(format="WWE '13 Wii (Experimental)",model='Costume '+f'{index:02d}',bytes=len(raw),
            meshes=model['mesh_count'],vertices=model['vertex_count'],triangles=model['triangle_count'],
            bones=model['bone_count'],textures=len(images),model_count=len(decode['models']),
            selected_entry=f'{index:02d}',source_sha256=hashlib.sha256(raw).hexdigest(),
            source_encoding_audit=decode['source_encoding_audit'],
            excluded_effects=decode['excluded_effects'],limitations='Unknown packet/rig layouts rejected; source blood animation is not converted.')
        if preview_folder is not None:
            from desktop.texture_review import source_previews
            result['texture_previews']=source_previews([(i,n,b'',im,dict(platform='Wii TPL')) for i,(n,im) in enumerate(zip(model['textures'],images))],preview_folder)
        if result['source_sha256']!=catalogue['source_sha256'] or path.read_bytes()!=raw:
            raise ValueError('Wii input changed during inspection; select it again.')
        return result
