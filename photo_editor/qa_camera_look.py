"""Write a temporary visual comparison, never modifying originals/catalogs."""
import sys
import numpy as np
from PIL import Image, ImageDraw
from camera_look import camera_look
from engine import load_image, embedded_thumbnail, _tone, normalize_recipe, linear_to_pil

path=sys.argv[1]
profile=camera_look(path)
raw=load_image(path,max_side=1200).pixels
images=[linear_to_pil(raw),linear_to_pil(_tone(raw,normalize_recipe({'camera_look':profile,'camera_look_enabled':True}))),embedded_thumbnail(path,1200,require_embedded=True)]
sheet=Image.new('RGB',(1500,560),'#181b1f');draw=ImageDraw.Draw(sheet)
for i,(im,label) in enumerate(zip(images,['Neutral RAW','Camera-inspired tone','Embedded camera JPEG'])):
    im.thumbnail((490,500));sheet.paste(im,(i*500+(500-im.width)//2,40+(500-im.height)//2));draw.text((i*500+12,12),label,fill='white')
sheet.save('/tmp/darkroom-camera-look-qa.jpg');print(profile)
