"""Minimum representations followed by measured marginal-quality-per-byte upgrades.

The callback rebuilds the actual PAC, including compression and alignment. This
is deterministic greedy allocation with a corrective downgrade pass, not a proof
of global optimality. Search never edits model data to create texture space.
"""


def allocate(choices,importance,build,target,max_pixels,cancel=lambda:None):
    selected=tuple(min(range(len(rows)),key=lambda i:(rows[i]['entry']['serialized_bytes'],
        rows[i]['entry']['metrics']['perceptual_loss'])) for rows in choices)
    cache={};decisions=[]
    def evaluate(selection):
        cancel()
        if selection not in cache:
            payload,allocation=build(selection)
            loss=sum(w*rows[i]['entry']['metrics']['perceptual_loss'] for w,rows,i in zip(importance,choices,selection))
            cache[selection]=(payload,dict(allocation,weighted_loss=loss))
        return cache[selection]
    def feasible(report):return report['pac_bytes']<=target and report['pixel_palette_bytes']<=max_pixels
    payload,current=evaluate(selected)
    # Raw GIM minima need not minimize BPE. Recover by actual serialized bytes,
    # with smallest priority-adjusted loss per recovered byte.
    for iteration in range(512):
        if feasible(current):break
        alternatives=[]
        for j,rows in enumerate(choices):
            for i,row in enumerate(rows):
                if i==selected[j]:continue
                candidate=selected[:j]+(i,)+selected[j+1:]
                _,report=evaluate(candidate)
                byte_saving=current['pac_bytes']-report['pac_bytes']
                mem_saving=current['pixel_palette_bytes']-report['pixel_palette_bytes']
                resource_saving=byte_saving if current['pac_bytes']>target else mem_saving
                if resource_saving<=0:continue
                loss=report['weighted_loss']-current['weighted_loss']
                alternatives.append((max(loss,0)/resource_saving,loss,candidate,report))
        if not alternatives:raise ValueError('Texture minimum safeguards cannot fit the actual PAC/pixel budget: current %d/%d PAC bytes, %d/%d pixel/CLUT bytes; geometry unchanged, export withheld'%(current['pac_bytes'],target,current['pixel_palette_bytes'],max_pixels))
        _,loss,selected,current=min(alternatives,key=lambda r:(r[0],r[1],r[2]))
        payload=cache[selected][0]
        decisions.append(dict(action='serialized-budget-recovery',selection=list(selected),loss=loss,**current))
    else:raise ValueError('Budget recovery did not converge; export withheld')
    # A round considers every improving option independently. Measured PAC byte
    # costs, rather than width*height, choose the best feasible marginal return.
    for iteration in range(512):
        alternatives=[]
        for j,rows in enumerate(choices):
            before=rows[selected[j]]['entry']
            for i,row in enumerate(rows):
                improvement=importance[j]*(before['metrics']['perceptual_loss']-row['entry']['metrics']['perceptual_loss'])
                if improvement<=1e-10:continue
                candidate=selected[:j]+(i,)+selected[j+1:]
                _,report=evaluate(candidate)
                extra=report['pac_bytes']-current['pac_bytes']
                ratio=improvement/max(extra,1)
                if feasible(report):alternatives.append((ratio,improvement,extra,j,i,candidate,report))
        if not alternatives:break
        ratio,gain,extra,j,i,selected,current=max(alternatives,key=lambda r:(r[0],r[1],-r[2],-r[3],-r[4]))
        payload=cache[selected][0]
        decisions.append(dict(action='quality-upgrade',texture_index=j,candidate_index=i,
            important_information_restored=gain,additional_serialized_pac_bytes=extra,
            value_per_byte=ratio,selection=list(selected),**current))
    else:raise ValueError('Upgrade allocation did not converge; export withheld')
    if not feasible(current):raise ValueError('Final serialized size enforcement failed')
    # Report why every unselected next upgrade is rejected, using exact bytes.
    rejected=[]
    for j,rows in enumerate(choices):
        for i,row in enumerate(rows):
            if i==selected[j]:continue
            benefit=importance[j]*(rows[selected[j]]['entry']['metrics']['perceptual_loss']-row['entry']['metrics']['perceptual_loss'])
            if benefit<=1e-10:reason='No priority-adjusted quality improvement over selected candidate'
            else:
                _,r=evaluate(selected[:j]+(i,)+selected[j+1:])
                reason='Actual PAC size exceeds target' if r['pac_bytes']>target else 'Padded pixel/CLUT budget exceeded' if r['pixel_palette_bytes']>max_pixels else 'Feasible upgrade remains: review search'
            record=dict(texture_index=j,candidate_index=i,reason=reason,priority_adjusted_improvement=benefit)
            if benefit>1e-10:record.update(proposed_pac_bytes=r['pac_bytes'],proposed_pixel_palette_bytes=r['pixel_palette_bytes'],additional_pac_bytes=r['pac_bytes']-current['pac_bytes'])
            rejected.append(record)
    return payload,selected,dict(current,decisions=decisions,rejected_upgrades=rejected,
        measured_combinations=len(cache),target_bytes=target,unused_bytes=target-current['pac_bytes'],
        algorithm='Safe minimum then exact-PAC marginal gain/byte; deterministic greedy, not global optimum')
