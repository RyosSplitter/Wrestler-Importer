"""Shared converter/batch wording for the measured final-export seam audit."""


def seam_status(result):
    row=result.get('export_seams')
    if not row:
        return ''
    return (f"Seams: {row['review_findings']} findings; {row['unmatched_sides']} unmatched/ambiguous checks — see QA report")


def save_warning(result):
    status=seam_status(result)
    return (f"The QA report has {result['review_flags']} review findings."
            +(f"\n{status}." if status else '')
            +'\nThis candidate still needs PPSSPP testing. Save it as an experimental PAC?')
