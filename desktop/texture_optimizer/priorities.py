"""Texture-only exchange search starting from the accepted Default allocation.

Selected maps never lose quality. Unselected maps fund an upgrade only when
the combined priority-weighted gain is positive, under the same measured PAC
and padded pixel/CLUT envelope. This bounded greedy search is not an optimum.
"""


def allocate_priorities(choices, importance, build, target, max_pixels,
                        initial, priority_indices, cancel=lambda: None):
    selected=tuple(initial);priority_indices=set(priority_indices)
    cache={};decisions=[]
    def evaluate(selection):
        cancel()
        if selection not in cache:
            payload,allocation=build(selection)
            loss=sum(w*rows[i]['entry']['metrics']['perceptual_loss']
                     for w,rows,i in zip(importance,choices,selection))
            cache[selection]=(payload,dict(allocation,weighted_loss=loss))
        return cache[selection]
    def feasible(report):
        return report['pac_bytes']<=target and report['pixel_palette_bytes']<=max_pixels
    payload,current=evaluate(selected)
    if not feasible(current):
        raise ValueError('Priority reallocation requires a fitting, validated baseline; geometry unchanged')

    def funded(proposal):
        """Reclaim resources from ordinary maps; never downgrade a selection.

        Rank all donor changes by their quality cost and measured individual
        GIM storage/pixel savings, then serialize the six best proposals plus
        the largest resource recovery. Whole-PAC compression is non-additive;
        accept changes only by the actual serialized result.
        """
        _,state=evaluate(proposal);trail=[]
        for _ in range(128):
            if feasible(state):return proposal,state,trail
            need_pixels=state['pixel_palette_bytes']>max_pixels
            options=[]
            for j,rows in enumerate(choices):
                if j in priority_indices:continue
                before=rows[proposal[j]]['entry']
                for i,row in enumerate(rows):
                    if i==proposal[j]:continue
                    entry=row['entry']
                    # Resource usage must be monotone in the donor path. The
                    # PAC is still measured: GIM savings do not imply BPE savings.
                    if entry['pixel_palette_bytes']>before['pixel_palette_bytes']:continue
                    saving=(before['pixel_palette_bytes']-entry['pixel_palette_bytes'] if need_pixels
                            else before['serialized_bytes']-entry['serialized_bytes'])
                    if saving<=0 and not (not need_pixels and
                        entry['metrics']['perceptual_loss']<before['metrics']['perceptual_loss']):continue
                    loss=importance[j]*(entry['metrics']['perceptual_loss']-before['metrics']['perceptual_loss'])
                    options.append((max(loss,0)/max(saving,1),loss,-saving,j,i))
            if not options:return None
            shortlist=sorted(options)[:6]
            largest=min(options,key=lambda r:(r[2],r[1],r[3],r[4]))
            if largest not in shortlist:shortlist.append(largest)
            measured=[]
            for _,loss,_,j,i in shortlist:
                candidate=proposal[:j]+(i,)+proposal[j+1:]
                _,r=evaluate(candidate)
                recovered=(state['pixel_palette_bytes']-r['pixel_palette_bytes'] if need_pixels
                           else state['texture_stored_bytes']-r['texture_stored_bytes'])
                if recovered<=0:continue
                measured.append((max(loss,0)/recovered,loss,-recovered,j,i,candidate,r))
            if not measured:return None
            _,loss,_,j,i,proposal,state=min(measured,key=lambda r:r[:5])
            trail.append(dict(texture_index=j,candidate_index=i,weighted_loss=loss))
        raise ValueError('Priority donor search did not converge; export withheld')

    for _ in range(128):
        alternatives=[]
        for j in sorted(priority_indices):
            before=choices[j][selected[j]]['entry']
            for i,row in enumerate(choices[j]):
                gain=importance[j]*(before['metrics']['perceptual_loss']-row['entry']['metrics']['perceptual_loss'])
                if gain<=1e-10:continue
                proposal=selected[:j]+(i,)+selected[j+1:]
                result=funded(proposal)
                if result is None:continue
                candidate,state,donors=result
                net=current['weighted_loss']-state['weighted_loss']
                if net<=1e-10:continue
                # Account for uncompressed texture RAM as well as disk space;
                # padding/compression plateaus must not create infinite value.
                extra=max(state['texture_stored_bytes']-current['texture_stored_bytes'],
                          row['entry']['pixel_palette_bytes']-before['pixel_palette_bytes'],1)
                alternatives.append((net/extra,net,gain,-j,-i,candidate,state,donors))
        if not alternatives:break
        ratio,net,gain,nj,ni,selected,current,donors=max(alternatives,key=lambda r:r[:5])
        payload=cache[selected][0]
        decisions.append(dict(action='priority-funded-upgrade',texture_index=-nj,candidate_index=-ni,
            priority_quality_gain=gain,net_weighted_quality_gain=net,value_per_byte=ratio,
            donor_changes=donors,selection=list(selected),**current))
    else:raise ValueError('Priority exchange allocation did not converge; export withheld')
    if not feasible(current):raise ValueError('Final priority serialized size enforcement failed')
    rejected=[]
    for j in sorted(priority_indices):
        before=choices[j][selected[j]]['entry']
        for i,row in enumerate(choices[j]):
            gain=importance[j]*(before['metrics']['perceptual_loss']-row['entry']['metrics']['perceptual_loss'])
            if gain<=1e-10:continue
            result=funded(selected[:j]+(i,)+selected[j+1:])
            reason=('No compatible donor combination found within PAC/pixel budgets' if result is None
                    else 'Donor quality cost outweighs selected gain' if result[1]['weighted_loss']>=current['weighted_loss']-1e-10
                    else 'Feasible exchange remains: bounded search requires review')
            rejected.append(dict(texture_index=j,candidate_index=i,reason=reason,
                                 priority_adjusted_improvement=gain))
    return payload,selected,dict(current,decisions=decisions,rejected_upgrades=rejected,
        measured_combinations=len(cache),target_bytes=target,unused_bytes=target-current['pac_bytes'],
        algorithm='Default incumbent plus measured priority/donor exchanges; deterministic bounded greedy, not global optimum')
