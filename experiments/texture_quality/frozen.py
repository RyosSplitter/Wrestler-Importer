"""Texture-only edits to an exact PSP PAC, preserving every geometric byte."""
import hashlib
import struct

from desktop.core import validate_pac
from desktop.accessories import combined_preview
from tools.pac_inspect import inspect_pac,parse_textures
from tools.pac_repack import replace_sections,texture_table
from tools.psp_mesh_audit import audit_yobj
from tools.psp_mesh_merge_trial import sections
from tools.texture_convert import read_gim
from tools.yukes_bpe import compress,decompress


def digest(data):return hashlib.sha256(data).hexdigest()


class FrozenPac:
    def __init__(self,data,max_bytes=148000,max_texture_bytes=52992):
        self.data=data;self.max_bytes=max_bytes;self.max_texture_bytes=max_texture_bytes
        self.sections={s['id']:(s,raw) for s,raw in sections(data)}
        self.models={i:audit_yobj(raw) for i,(s,raw) in self.sections.items() if raw.startswith(b'YOBJ')}
        self.names=self.models[2]['texture_names']
        table=self.sections[9][1]
        self.gims={t['name']:table[t['offset']:t['offset']+t['size']] for t in parse_textures(table)}
        self.retained_texture_bytes=0
        for i,(s,raw) in self.sections.items():
            if i!=9 and len(raw)>=16 and raw[4:16]==struct.pack('<3I',256,0,16):
                for t in parse_textures(raw):
                    indices,palette=read_gim(raw[t['offset']:t['offset']+t['size']])
                    self.retained_texture_bytes+=indices.size*(4 if len(palette)==16 else 8)//8+palette.size
        self.preview=combined_preview(self.models[2],[self.models[i] for i in sorted(self.models) if i!=2])
        self.cache={}

    def update_model(self,section,bits):
        source=self.sections[section][1];model=self.models[section];out=bytearray(source);allowed=set();changes=[]
        mesh_start=struct.unpack_from('<I',source,36)[0]+8
        for mesh in model['meshes']:
            ma=struct.unpack_from('<I',source,mesh_start+mesh['index']*64+12)[0]+8
            for mi,mat in enumerate(mesh['materials']):
                old=mat['control'];name=model['texture_names'][mat['texture_id']]
                if old not in (5,7,0x115,0x117):raise ValueError('Unrecognized experimental material contract')
                new=(old&~0x7)|(5 if bits[name]==4 else 7)
                if new!=old:
                    at=ma+mi*144+24;struct.pack_into('<I',out,at,new);allowed.update(range(at,at+4))
                    changes.append(dict(mesh=mesh['index'],material=mi,texture=name,offset=at,before=hex(old),after=hex(new)))
        output=bytes(out)
        if any(a!=b and i not in allowed for i,(a,b) in enumerate(zip(source,output))):raise ValueError('Non-material YOBJ data changed')
        audited=audit_yobj(output)
        if audited['bone_raw']!=model['bone_raw']:raise ValueError('Skeleton changed')
        for a,b in zip(model['meshes'],audited['meshes']):
            if a['raw_vertices']!=b['raw_vertices'] or a['bone_palette']!=b['bone_palette'] or a['raw_header']!=b['raw_header']:raise ValueError('Geometry, UV, normal, weights, palette or metadata changed')
            for am,bm in zip(a['materials'],b['materials']):
                if am['strips']!=bm['strips'] or am['strip_headers']!=bm['strip_headers'] or am['triangles']!=bm['triangles']:raise ValueError('Topology changed')
        return output,changes

    def build(self,gims):
        if set(gims)!=set(self.names):raise ValueError('Texture name set changed')
        bits={n:4 if len(read_gim(raw)[1])==16 else 8 for n,raw in gims.items()}
        key=tuple(bits[n] for n in self.names)
        if key not in self.cache:
            replacements={};models=[]
            for section in sorted(self.models):
                raw,changes=self.update_model(section,bits)
                original=self.sections[section][1]
                s=self.sections[section][0]
                if raw!=original:
                    replacements[section]=compress(raw)
                models.append(dict(section=section,original_yobj_sha256=digest(original),yobj_sha256=digest(raw),
                                   material_control_changes=changes,all_other_yobj_bytes_identical=True,
                                   geometric_buffers_weights_skeleton_topology_identical=True))
            self.cache[key]=(replacements,models)
        updates,model_proof=self.cache[key];updates=dict(updates)
        raw_table=texture_table(self.names,[gims[n] for n in self.names])
        updates[9]=compress(raw_table)
        pac=replace_sections(self.data,updates)
        # Validate structural constraints independently of the policy ceiling.
        native,actual=validate_pac(pac,max_bytes=max(len(pac),self.max_bytes))
        if actual!=gims:raise ValueError('Texture table roundtrip differs')
        after={s['id']:(s,raw) for s,raw in sections(pac)}
        for i,(s,raw) in self.sections.items():
            if i not in updates and after[i][0]['sha256']!=s['sha256']:raise ValueError('Unrelated stored PAC section changed')
            if i in self.models and digest(after[i][1])!=next(m['yobj_sha256'] for m in model_proof if m['section']==i):raise ValueError('Model BPE roundtrip differs')
        memory=self.retained_texture_bytes
        for raw in gims.values():
            indices,palette=read_gim(raw);memory+=indices.size*(4 if len(palette)==16 else 8)//8+palette.size
        sizes=inspect_pac(pac)['sections']
        report=dict(pac_bytes=len(pac),sha256=digest(pac),texture_section_stored_bytes=len(updates[9]),
                    texture_section_decoded_bytes=len(raw_table),encoded_gim_bytes=sum(map(len,gims.values())),
                    texture_pixel_palette_bytes=memory,retained_texture_pixel_palette_bytes=self.retained_texture_bytes,
                    model_stored_bytes=sum(s['size'] for s in sizes if s['id'] in self.models),
                    model_decoded_bytes=sum(len(after[i][1]) for i in self.models),
                    structural_validation='PASS: native pointers, buffers, indices, palette entries, normalized weights, POF relocation, material-profile pairing, outer ranges/alignment and BPE roundtrips',
                    model_proofs=model_proof,
                    pac_budget_pass=len(pac)<=self.max_bytes,pac_budget_bytes=self.max_bytes,
                    texture_observed_envelope_pass=memory<=self.max_texture_bytes,
                    texture_observed_envelope_bytes=self.max_texture_bytes,
                    envelope_scope='Native Rock aggregate swizzled pixels and palettes; inferred experimental envelope, not validated runtime heap limit',
                    in_game_validation='PENDING')
        report['export_eligible']=report['pac_budget_pass'] and report['texture_observed_envelope_pass']
        return pac,report
