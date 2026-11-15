import sys,json
sys.path.insert(0,'.')
from crop import cord,page_img,key
from PIL import Image,ImageDraw,ImageFont
f=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',22)
def zoom(v,a,lab=''):
    pg=key(a)[0]; P=next(p for p in cord(v)['pages'] if p['page']==pg); img=page_img(v,pg)
    sx=img.width/P['canvas']['width']
    c=next(c for c in P['cells'] if c['a']==a)
    x,y,w,h=c['box']; m=int(w*0.25)
    im=img.crop((int((x-m)*sx),int((y-m)*sx),int((x+w+m)*sx),int((y+h+m)*sx))).resize((260,int(260*(h+2*m)/(w+2*m))))
    can=Image.new('RGB',(270,im.height+30),'white'); can.paste(im,(0,30)); ImageDraw.Draw(can).text((2,2),lab or a,fill=0,font=f); return can
if __name__=="__main__":
  out=sys.argv[1]; ims=[zoom(*s.split('@')) for s in sys.argv[2:]]
  can=Image.new("RGB",(280*len(ims),max(i.height for i in ims)),'white')
  for k,i in enumerate(ims): can.paste(i,(280*k,0))
  can.save(out)
