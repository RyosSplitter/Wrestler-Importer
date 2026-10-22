"""Cached visible-surface shading for color-only edits with immutable UV/alpha.

Geometry/camera changes rebuild the cache. Paint, recolor, layer placement and
palette changes only resample current textures. Cutout visibility is fixed because
the document locks every original alpha sample and texture dimension.
"""
import numpy as np
from PIL import Image,ImageDraw
from desktop.preview import render


class TexturePreview:
    def __init__(self,model,images,*,yaw=35,zoom=1.,resolution=480):
        self.names=list(model['texture_names']);self.resolution=resolution;self.yaw=yaw
        self.shapes={n:images[n].shape for n in self.names}
        self.alpha={n:images[n][:,:,3].copy()for n in self.names}
        self.capture={}
        render(model,{},resolution=resolution,zoom=zoom,rgba_textures=images,yaw=yaw,capture=self.capture)
        self.groups=[]
        for i,name in enumerate(self.names):
            mask=self.capture['texture']==i
            self.groups.append((name,mask,self.capture['address'][mask],
                                self.capture['vertex_color'][mask],self.capture['shade'][mask,None]))
        del self.capture

    def image(self,images,highlight=None):
        pixels=np.full((self.resolution,self.resolution,3),72,np.uint8)
        for name,mask,address,color,shade in self.groups:
            texture=images[name]
            if texture.shape!=self.shapes[name]or not np.array_equal(texture[:,:,3],self.alpha[name]):
                raise ValueError('Live preview cache requires unchanged texture dimensions/alpha.')
            sampled=texture.reshape(-1,4)[address,:3].astype(float)
            rgb=np.clip(sampled*color*shade,0,255).astype(np.uint8)
            if highlight is not None and name!=highlight:
                rgb=np.repeat(rgb.mean(axis=1,keepdims=True)*.35,3,axis=1).astype(np.uint8)
            pixels[mask]=rgb
        image=Image.fromarray(pixels);draw=ImageDraw.Draw(image)
        draw.text((14,14),'PSP OUTPUT | LIVE ORBIT %.0f DEG'%self.yaw,fill='white')
        draw.text((14,self.resolution-25),'Offline preview | game shading may differ',fill='white')
        return image
