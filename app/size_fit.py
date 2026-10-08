"""Select a smaller uniform-collapse ratio when a source exceeds the PAC cap."""
import math


def next_ratio(ratio, pac_bytes, model_bytes, limit):
    overhead = pac_bytes - model_bytes
    available = limit - overhead - 2048  # Leave one archive padding block.
    if available <= 0 or model_bytes <= 0:
        raise ValueError('Textures and unchanged base sections leave no model space within the PAC limit.')
    candidate = math.floor(min(ratio * 0.9, ratio * available / model_bytes * 0.98) * 1000) / 1000
    if candidate < 0.1 or candidate >= ratio:
        raise ValueError('This source cannot fit the PAC limit without reducing below the beta quality floor (ratio 0.1).')
    return candidate
