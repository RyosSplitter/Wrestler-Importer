"""Validate HCTP packet contracts, independent of character names or file hashes."""
from pathlib import Path
from app.ps2_textures import read_source
from tools.hctp_weights import load_hctp_with_weights
from tools.pac_inspect import inspect_pac

class HctpAdapter:
    key='hctp'
    def read(self,path):
        path=Path(path)
        if path.suffix.lower()!='.pac': raise ValueError('Choose a .pac file.')
        if path.stat().st_size>32*1024*1024: raise ValueError('This PAC exceeds the supported 32 MiB input budget.')
        data=path.read_bytes()
        inspect_pac(data)
        model=load_hctp_with_weights(path)
        textures=read_source(path)
        if not model['triangle_count']: raise ValueError('The HCTP PAC contains no supported model triangles.')
        return model,textures
    def inspect(self,path,preview_folder=None):
        import hashlib
        fingerprint=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        model,textures=self.read(path)
        from desktop.accessories import source_models,decode_dependencies
        accessories,names=source_models(Path(path),model)
        textures=decode_dependencies(Path(path),textures,names)
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=fingerprint:
            raise ValueError('Source changed during texture inspection; select it again.')
        result={'format':'HCTP PS2','model':model['model_name'],'bytes':Path(path).stat().st_size,
                'meshes':model['mesh_count'],'vertices':model['source_vertex_count'],
                'triangles':model['triangle_count'],'bones':model['bone_count'],'textures':len(names),
                'model_count':1+len(accessories),'accessory_sections':[a['source_section'] for a in accessories],
                'source_sha256':fingerprint}
        if preview_folder is not None:
            from desktop.texture_review import source_previews
            result['texture_previews']=source_previews(textures,preview_folder)
        return result
