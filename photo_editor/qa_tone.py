"""Repeatable visual regression sheet; does not write originals or catalogs."""
import sys
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw,ImageOps
from engine import load_image,process

def main(destination):
    cases=['DSCF2820.RAF','DSCF2838.RAF','DSCF2915.RAF']
    settings=[('Neutral',{}),('Shadows +100',{'shadows':100}),('Exposure +3 EV',{'exposure':3}),('Highlights -100',{'highlights':-100}),('Shadows +100 / Highlights -100',{'shadows':100,'highlights':-100})]
    sheet=Image.new('RGB',(1500,3*360),(24,29,33));draw=ImageDraw.Draw(sheet)
    for row,name in enumerate(cases):
        source=load_image(Path('/Volumes/SU800/Ari')/name,max_side=900)
        for col,(label,r) in enumerate(settings):
            image=process(source,{**r,'sharpen':0,'denoise':0},apply_crop=False,preview=True)
            tile=ImageOps.contain(image,(290,315))
            sheet.paste(tile,(col*300+(300-tile.width)//2,row*360+38))
            draw.text((col*300+6,row*360+5),name,fill='white')
            draw.text((col*300+6,row*360+20),label,fill='#bdccda')
    sheet.save(destination)
    print(destination)

if __name__=='__main__':main(sys.argv[1])
