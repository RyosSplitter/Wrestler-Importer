"""JBI's observed DPAC/costume + TIM2 family; never an HCTP/SYM alias."""
from pathlib import Path

from tools.jbi_source import decoded_textures,read,select
from tools.sym_source import sha


class JbiAdapter:
    key='jbi'

    def catalogue(self,path):
        raw=Path(path).read_bytes()
        return select(raw)[1]

    def read(self,path,entry_id=''):
        bundle=read(Path(path).read_bytes(),entry_id)
        return bundle['charted'],decoded_textures(bundle)

    def inspect(self,path,preview_folder=None,entry_id=''):
        path=Path(path);data=path.read_bytes();bundle=read(data,entry_id)
        model=bundle['originals'][2];selection=bundle['selection']
        result=dict(format='JBI PS2',model=model['model_name'],bytes=len(data),
            meshes=model['mesh_count'],vertices=model['source_vertex_count'],triangles=model['triangle_count'],
            bones=model['bone_count'],textures=len(bundle['images']),model_count=len(bundle['originals']),
            accessory_sections=[sid for sid in bundle['originals'] if sid!=2],**selection)
        if preview_folder is not None:
            from desktop.texture_review import source_previews
            result['texture_previews']=source_previews(decoded_textures(bundle),preview_folder)
        if sha(path.read_bytes())!=selection['source_sha256']:
            raise ValueError('JBI source changed during inspection; select it again.')
        return result
