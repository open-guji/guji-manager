"""D01/D02 拼图：python3 d_sheet.py x <with_ref|no_ref> [<参校字集合>|-|!<要排除的字>] [每张格数]；每格显示裁图、整理本字、库首位及分、整理本前后文。读 crops/ 下裁好的图。"""
import csv,sys,json
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
F=ImageFont.truetype('/usr/share/fonts/opentype/unifont/unifont.otf',16)
FS=ImageFont.truetype('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc',16)
rows=[r for r in csv.DictReader(open('/home/user/ai-team/domain/CV/质检/待审清单-2026-11-07-r7/按码-逐格.tsv'),delimiter='\t') if r['reason'].startswith('occluded')]
sel=sys.argv[2]; rows=[r for r in rows if r['reason'].endswith(sel)]
if len(sys.argv)>3 and sys.argv[3]!="-": rows=[r for r in rows if r["ref"] not in sys.argv[3][1:]] if sys.argv[3].startswith("!") else [r for r in rows if r["ref"] in sys.argv[3]]
N=int(sys.argv[4]) if len(sys.argv)>4 else 12
CW=170; CH=250
for s in range(0,len(rows),N):
    chunk=rows[s:s+N]; cols=6; rr=(len(chunk)+cols-1)//cols
    sheet=Image.new('RGB',(cols*CW,rr*CH),'white'); d=ImageDraw.Draw(sheet)
    for i,r in enumerate(chunk):
        x=(i%cols)*CW; y=(i//cols)*CH
        p=Path(f"/home/user/d2/crops/{r['vol']}_{r['cell'].replace(':','_')}.png")
        if p.exists():
            im=Image.open(p).convert('RGB'); im.thumbnail((CW-10,150)); sheet.paste(im,(x+5,y+22))
        d.text((x+3,y+2),f"{s+i+1} {r['vol']}:{r['cell']}",fill='red',font=FS)
        d.text((x+3,y+176),f"参={r['ref'] or '-'} 库={r['top'][:14]}",fill='blue',font=FS)
        d.text((x+3,y+196),f"{r['L'][-5:]}[ ]{r['R'][:5]}",fill='black',font=FS)
    sheet.save(f"/home/user/d2/sheet_{sel}_{s//N+1}.png")
    print(s//N+1)
