"""Explicit texture-domain measures; they do not certify runtime appearance."""
import math
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel


def compare(reference,candidate):
    if candidate.shape!=reference.shape:
        candidate=np.asarray(Image.fromarray(candidate).resize((reference.shape[1],reference.shape[0]),Image.Resampling.LANCZOS))
    a=reference[:,:,:3].astype(float)/255;b=candidate[:,:,:3].astype(float)/255
    alpha=reference[:,:,3].astype(float)/255;mass=max(float(alpha.sum()),1e-12)
    sq=((a-b)**2).mean(2);mse=float((sq*alpha).sum()/mass)
    ya=a@np.array([.2126,.7152,.0722]);yb=b@np.array([.2126,.7152,.0722])
    ma=gaussian_filter(ya,1.5);mb=gaussian_filter(yb,1.5)
    va=np.maximum(gaussian_filter(ya*ya,1.5)-ma*ma,0);vb=np.maximum(gaussian_filter(yb*yb,1.5)-mb*mb,0)
    cov=gaussian_filter(ya*yb,1.5)-ma*mb
    ssim=((2*ma*mb+.01**2)*(2*cov+.03**2))/((ma*ma+mb*mb+.01**2)*(va+vb+.03**2))
    ga=np.hypot(sobel(ya,0),sobel(ya,1));gb=np.hypot(sobel(yb,0),sobel(yb,1))
    edge=float((np.abs(ga-gb)*alpha).sum()/mass)
    salient=alpha*(1+2*np.minimum(ga,1))
    weighted=float((sq*salient).sum()/max(float(salient.sum()),1e-12))
    result=dict(rgb_rmse_255=math.sqrt(mse)*255,psnr_db=None if mse==0 else -10*math.log10(mse),
                exact_rgb=mse==0,luminance_ssim=float((ssim*alpha).sum()/mass),
                sobel_magnitude_mae=edge,edge_weighted_rgb_mse=weighted,
                alpha_mae=float(np.abs(reference[:,:,3].astype(float)-candidate[:,:,3]).mean()),
                alpha_coverage_delta=float((candidate[:,:,3]>=128).mean()-(reference[:,:,3]>=128).mean()),
                metric_resampling='Candidate decoded RGBA reconstructed to source dimensions using Lanczos',
                ssim_definition='Gaussian sigma 1.5, C1=.01^2, C2=.03^2, luminance [0,1], alpha-weighted',
                loss=weighted+.003*(1-float((ssim*alpha).sum()/mass))+.0005*edge)
    return result


def encode(reference,size,bits):
    """Resize RGBA once; choose the best supported Pillow RGB quantizer.

    Nonopaque RGBA is exact-only. Do not silently invent an alpha policy.
    """
    from tools.texture_convert import write_gim4,write_gim8,read_gim
    target=np.asarray(Image.fromarray(reference).resize(size,Image.Resampling.LANCZOS))
    if np.any(reference[:,:,3]!=255):
        if size!=(reference.shape[1],reference.shape[0]):raise ValueError('Alpha textures are exact-resolution-only in this experiment')
        colors,inverse=np.unique(reference.reshape(-1,4),axis=0,return_inverse=True)
        if len(colors)>1<<bits:raise ValueError('Exact RGBA palette does not fit selected bit depth')
        palette=np.zeros((1<<bits,4),dtype=np.uint8);palette[:len(colors)]=colors
        indices=inverse.reshape(reference.shape[:2]).astype(np.uint8);method='Exact RGBA palette'
    else:
        rgb=Image.fromarray(target[:,:,:3]);choices=[]
        for method in (Image.Quantize.MEDIANCUT,Image.Quantize.MAXCOVERAGE,Image.Quantize.FASTOCTREE):
            q=rgb.quantize(colors=1<<bits,method=method,dither=Image.Dither.NONE)
            indices=np.asarray(q,dtype=np.uint8)
            colors=np.asarray(q.getpalette(),dtype=np.uint8).reshape(-1,3)
            palette=np.zeros((1<<bits,4),dtype=np.uint8);palette[:,3]=255;palette[:len(colors),:3]=colors
            metric=compare(reference,palette[indices])
            choices.append((metric['loss'],int(method),indices,palette))
        _,method,indices,palette=min(choices,key=lambda t:(t[0],t[1]))
        method={0:'Median cut',1:'Maximum coverage',2:'Fast octree'}[method]
    raw=(write_gim4 if bits==4 else write_gim8)(indices,palette)
    back,colors=read_gim(raw)
    if not np.array_equal(back,indices) or not np.array_equal(colors,palette):raise ValueError('GIM roundtrip changed quantized image')
    rgba=colors[back]
    if np.any(reference[:,:,3]!=255) and not np.array_equal(reference,rgba):raise ValueError('RGBA preservation failed')
    return raw,rgba,dict(width=size[0],height=size[1],bits=bits,palette_entries=1<<bits,
                         used_palette_entries=len(np.unique(back)),unique_decoded_rgba_colors=len(np.unique(rgba.reshape(-1,4),axis=0)),
                         encoded_bytes=len(raw),pixel_palette_bytes=indices.size*bits//8+len(palette)*4,
                         aspect_ratio=size[0]/size[1],quantizer=method,metrics=compare(reference,rgba))
