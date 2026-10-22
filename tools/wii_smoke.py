"""Frozen Windows Wii GUI/worker smoke using procedural GCTC/TPL panels."""
import json
from pathlib import Path
import time
from PIL import ImageGrab
from desktop.storage import save_as
from tools.wii_fixture import create
from tools.sym_source import sha
from tools.wwe13_wii_trial import validate_trial


def run(app,output,base):
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True)
    source=create(base,output.parent/'fixtures');original=source.read_bytes();original_base=Path(base).read_bytes()
    from tkinter import messagebox
    errors=[];old_error=messagebox.showerror
    messagebox.showerror=lambda title,message,**kw:errors.append((title,message))
    def wait(predicate,timeout=480):
        start=time.monotonic()
        while not predicate():
            app.root.update()
            if errors:raise ValueError(str(errors[-1]))
            if time.monotonic()-start>timeout:raise TimeoutError('Frozen Wii job timed out: '+app.status.get())
            time.sleep(.03)
        app.root.update()
        if errors:raise ValueError(str(errors[-1]))
    try:
        # Exercise the Road Dogg layout in the frozen worker using procedural
        # geometry; retain the existing complete conversion control below.
        mixed=create(base,output.parent/'mixed-packet-fixtures',mixed_packets=True)
        mixed_original=mixed.read_bytes()
        app.choose_source_format('wwe13-wii');app.select_source(mixed);wait(lambda:app.inspector is None)
        audit=app.source_inspection['source_encoding_audit']
        assert audit['status']=='pass' and len(audit['packets'])==6
        assert [r['position_divisor']for r in audit['packets']]==[256,256,128]*2
        assert mixed.read_bytes()==mixed_original
        app.choose_source_format('wwe13-wii');app.select_source(source);wait(lambda:app.inspector is None)
        assert app.source_format.get()=='wwe13-wii'
        assert tuple(app.source_entry_dropdown.cget('values'))==('00','01')
        assert tuple(app.texture_dropdown.cget('values'))==('Default',)
        assert app.costume_role.get()=='ring'
        assert not app.wii_seam_protection.get() and app.wii_seam_row.winfo_ismapped()
        app.wii_seam_checkbox.invoke();assert app.wii_seam_protection.get()
        app.source_entry.set('01');app.change_source_entry();wait(lambda:app.inspector is None)
        assert app.source_inspection['selected_entry']=='01'
        scales=app.source_inspection['source_encoding_audit']
        assert scales['status']=='pass'
        assert {r['position_divisor']for r in scales['packets']}=={128,256}
        app.base.set(str(Path(base).resolve()));app.costume_role.set('entrance');app.start()
        assert app.conversion_timer.status=='running' and 'Estimated remaining:'in app.timer_text.get()
        wait(lambda:not app.busy())
        assert app.result is not None,app.status.get()
        assert app.conversion_timer.status=='completed' and 'Completed in 'in app.timer_text.get()
        from desktop.conversion_timer import read_history
        from desktop.storage import data_dir
        before_timings=len(read_history(data_dir()/'conversion-timings.json').get(app.timing_profile,[]))
        assert before_timings>0
        result=app.result;raw=Path(result['pac']).read_bytes();work=Path(result['pac']).parent
        checks=json.loads((work/'wii/native-checks.json').read_text());ocular=json.loads((work/'wii/ocular.json').read_text())
        validate_trial(raw,(work/'storage-reference.pac').read_bytes(),checks['radius_changes'],ocular['source_controller_pivot_fit'],costume_role='entrance')
        assert result['source_entry']=='01' and result['costume_role']=='entrance'
        assert result['wii_seam_protection']
        reduced=json.loads((work/'wii/reduced.json').read_text())
        assert reduced['reduction_report']['source_uv_seam_scope']==['Arms','Torso','Legs']
        assert reduced['reduction_report']['source_uv_seam_locks']
        assert 'Protect clothing seams: enabled' in Path(result['report']).read_text(encoding='utf-8')
        assert result['budget']['max_pac_bytes']==180000 and len(raw)<=180000
        assert app.preview.cget('image') and Path(result['report']).is_file()
        assert (work/'qa/opacity-support.json').is_file() and (work/'qa/palette-quality.json').is_file()
        save_as(result,output.parent/'procedural-wii-export.pac')
        assert (output.parent/'procedural-wii-export.pac').read_bytes()==raw
        app.root.update();x,y=app.root.winfo_rootx(),app.root.winfo_rooty()
        ImageGrab.grab().crop((x,y,x+app.root.winfo_width(),y+app.root.winfo_height())).save(output.parent/'wii-converted-preview.png')
        app.start();app.cancel_job();wait(lambda:not app.busy())
        failure=json.loads((app.job/'failure.json').read_text())
        assert failure['cancelled'] and not (app.job/'work').exists()
        assert app.conversion_timer.status=='cancelled'
        assert len(read_history(data_dir()/'conversion-timings.json').get(app.timing_profile,[]))==before_timings
        app.choose_source_format('hctp');app.root.update()
        assert 'ATO' in app.texture_dropdown.cget('values') and not app.costume_role_row.winfo_ismapped()
        assert not app.wii_seam_row.winfo_ismapped() and not app.wii_seam_protection.get()
        assert source.read_bytes()==original and Path(base).read_bytes()==original_base
        report=dict(status='pass',fixture='Procedural fixed-point GCTC panels/TPL images on caller-supplied development rig; no wrestler geometry or texture',
            platform_selection=True,costume_selection=True,explicit_entrance_budget=True,source_bone_decode=True,
            bundled_blender_conversion=True,full_static_analytical_head_hand_qa=True,final_pac_preview=True,
            mixed_q7_body_q8_auxiliary_decode_verified=True,
            three_packet_colorless_inspection=True,all_six_source_packets_audited=True,
            clothing_seam_checkbox=True,clothing_scope_passed_to_bundled_blender=True,
            seam_setting_reported=True,seam_control_hidden_and_reset_for_hctp=True,
            palette_and_alpha_reports=True,save_as_verified=True,cancellation_clean=True,hctp_options_restored=True,
            conversion_countdown=True,successful_timing_history=True,cancelled_run_not_learned=True,
            pac_bytes=len(raw),pac_sha256=sha(raw),inputs_unchanged=True,
            limitations='Hosted Windows frozen test; not a clean user Windows installation, real wrestler render or PPSSPP test.')
        output.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');return report
    finally:messagebox.showerror=old_error
