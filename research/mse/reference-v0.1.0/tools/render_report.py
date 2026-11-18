#!/usr/bin/env python3
"""Render the full audit/design Markdown with ReportLab; no network requests."""
from pathlib import Path
import hashlib
import html
import re
import subprocess
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph,
    Spacer, PageBreak, LongTable, TableStyle, Image, KeepTogether)
from reportlab.platypus.tableofcontents import TableOfContents
from matplotlib import mathtext

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'docs/MSE_ARCHITECTURE.md'
OUT=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'MSE_Architecture_v0.1.0.pdf'
TMP=ROOT/'tmp/pdfs'
TMP.mkdir(parents=True,exist_ok=True)
FONT=Path('/usr/share/fonts/truetype/dejavu')
for name,filename in [('Body','DejaVuSans.ttf'),('Bold','DejaVuSans-Bold.ttf'),
                      ('Italic','DejaVuSans-Oblique.ttf'),('Mono','DejaVuSansMono.ttf')]:
    pdfmetrics.registerFont(TTFont(name,str(FONT/filename)))
pdfmetrics.registerFontFamily('Body',normal='Body',bold='Bold',italic='Italic',boldItalic='Bold')
NAVY=colors.HexColor('#17324d'); TEAL=colors.HexColor('#097e88')
GRAY=colors.HexColor('#536477'); LIGHT=colors.HexColor('#eef4f7')
WIDTH=481.89
styles=getSampleStyleSheet()
styles.add(ParagraphStyle(name='TextMSE',fontName='Body',fontSize=9.1,leading=13.5,
                         textColor=NAVY,spaceAfter=7.5,splitLongWords=True))
styles.add(ParagraphStyle(name='H1MSE',fontName='Bold',fontSize=19,leading=24,
                         textColor=NAVY,spaceAfter=15,keepWithNext=True))
styles.add(ParagraphStyle(name='H2MSE',fontName='Bold',fontSize=12.5,leading=17,
                         textColor=TEAL,spaceBefore=13,spaceAfter=8,keepWithNext=True))
styles.add(ParagraphStyle(name='H3MSE',fontName='Bold',fontSize=10.2,leading=15,
                         textColor=NAVY,spaceBefore=9,spaceAfter=5,keepWithNext=True))
styles.add(ParagraphStyle(name='CellMSE',fontName='Body',fontSize=7.2,leading=10.3,
                         textColor=NAVY,splitLongWords=True))
styles.add(ParagraphStyle(name='HeadCellMSE',fontName='Bold',fontSize=7.4,leading=10.5,
                         textColor=colors.white,splitLongWords=True))
styles.add(ParagraphStyle(name='SmallMSE',fontName='Body',fontSize=7.8,leading=11,
                         textColor=GRAY,spaceAfter=6,splitLongWords=True))
styles.add(ParagraphStyle(name='CodeMSE',fontName='Mono',fontSize=7.4,leading=10.5,
                         textColor=NAVY,backColor=LIGHT,spaceAfter=7,
                         borderPadding=7,splitLongWords=True))

def inline(s):
    s=html.escape(s)
    s=s.replace('&lt;br/&gt;','<br/>')
    s=re.sub(r'\[([^\]]+)\]\((https?://[^\s)]+)\)',
             lambda m:'<link href="'+m[2]+'" color="#097e88">'+m[1]+'</link>',s)
    s=re.sub(r'`([^`]+)`',r'<font name="Mono" size="8">\1</font>',s)
    s=re.sub(r'\*\*([^*]+)\*\*',r'<b>\1</b>',s)
    return s

def para(s,style='TextMSE'):
    return Paragraph(inline(s),styles[style])

class Report(BaseDocTemplate):
    def __init__(self,path):
        super().__init__(str(path),pagesize=(595.28,841.89),leftMargin=56.7,
                         rightMargin=56.7,topMargin=62,bottomMargin=53,
                         title='MOTHER / COACH - Metabolic State Engine',
                         author='MSE architecture review',pageCompression=1)
        frame=Frame(self.leftMargin,self.bottomMargin,self.width,self.height,id='body')
        self.addPageTemplates(PageTemplate(id='main',frames=frame,onPage=self.chrome))
    def chrome(self,canvas,doc):
        canvas.saveState()
        if doc.page>1:
            canvas.setFont('Bold',7.4);canvas.setFillColor(NAVY)
            canvas.drawString(56.7,808,'MOTHER / COACH')
            canvas.setFont('Body',7.4);canvas.setFillColor(GRAY)
            canvas.drawRightString(538.58,808,'METABOLIC STATE ENGINE | v0.1.0')
            canvas.setStrokeColor(colors.HexColor('#d4e0e7'))
            canvas.line(56.7,797,538.58,797)
        canvas.setFont('Body',7.2);canvas.setFillColor(GRAY)
        canvas.drawString(56.7,31,'13 NOV 2026  |  OFFLINE RESEARCH PROTOTYPE')
        canvas.drawRightString(538.58,31,str(doc.page))
        canvas.restoreState()
    def afterFlowable(self,flow):
        if isinstance(flow,Paragraph) and getattr(flow,'toclevel',None) is not None:
            text=flow.getPlainText();key=hashlib.sha1(text.encode()).hexdigest()[:18]
            self.canv.bookmarkPage(key)
            self.canv.addOutlineEntry(text,key,level=flow.toclevel,closed=False)
            self.notify('TOCEntry',(flow.toclevel,text,self.page,key))

def diagram(which):
    if which==0:
        dot='''digraph G { graph [rankdir=TB,bgcolor="white",pad="0.15",nodesep="0.25",ranksep="0.35"];
        node [shape=box,style="rounded,filled",fillcolor="#eef4f7",color="#97b6c6",fontname="DejaVu Sans",fontsize=10,margin="0.14,0.10"];
        edge [color="#487389",arrowsize=.7,fontname="DejaVu Sans",fontsize=8];
        a [label="HealthKit JSON\nexisting collector"];
        b [label="Captured archive\nfuture durable outbox"];
        x [label="Qualified exports\nfuture sensor adapters"];
        g [label="Future VPS queue\nauthenticated relay",style="rounded,dashed"];
        r [label="MOTHER evidence archive\nPF001 feature",fillcolor="#d8eceb"];
        f [label="Versioned features\nand reproducible replay"];
        m [label="MSE state estimator\nnew component",fillcolor="#cce8e8"];
        k [label="E1 temporal\nresearch graph"];
        p [label="Reviewed immutable\nmechanism bundle"];
        s [label="State / uncertainty\nregistry"];
        c [label="COACH observation\nand experiment coordination"];
        e [label="Actual exposure\nand response evidence"];
        a->b; x->b; b->g [style=dashed,label="future upload"];g->r [style=dashed];b->r [label="offline read"];
        r->f;f->m;k->p;p->m;m->s;s->c;c->e;e->r [constraint=false];
        {rank=same;a;x;} {rank=same;f;k;} {rank=same;m;p;}
        }'''
    else:
        dot='''digraph G { graph [rankdir=TB,bgcolor="white",pad="0.2",nodesep="0.35",ranksep="0.35"];
        node [shape=box,style="rounded,filled",fillcolor="#eef4f7",color="#97b6c6",fontname="DejaVu Sans",fontsize=10,margin="0.16,0.12"];
        edge [color="#487389",arrowsize=.7,fontname="DejaVu Sans",fontsize=8];
        a [label="1. Local commit\npage + tombstones + anchor"];
        g [label="2. Gateway durable queue\nreceipt means queued only"];
        r [label="3. Authority commit\nrevisions + recoverable receipt",fillcolor="#d8eceb"];
        retry [label="Retry same key and bytes\nconflicting bytes rejected"];
        raw [label="4. Revision notice\nversioned evidence snapshot"];
        m [label="5. Features + state estimate\nuncertainty and unknowns",fillcolor="#cce8e8"];
        q [label="6. COACH measurement request\nactual exposure / response"];
        invalid [label="Correction or deletion\ninvalidate affected derived runs"];
        a->g;g->r;g->retry [label="no authority receipt"];retry->r;r->a [label="authority receipt",constraint=false];
        r->raw;raw->m;m->q;q->r [label="new evidence",constraint=false];raw->invalid;invalid->m [label="replay"];
        {rank=same;g;retry;} {rank=same;raw;invalid;}
        }'''
    src=TMP/f'diagram-{which}.dot';png=TMP/f'diagram-{which}.png'
    src.write_text(dot)
    subprocess.run(['dot','-Tpng','-Gdpi=170',str(src),'-o',str(png)],check=True)
    w,h=ImageReader(str(png)).getSize();scale=min(WIDTH/w,495/h)
    return Image(str(png),width=w*scale,height=h*scale,hAlign='CENTER')

def equation(text,index):
    path=TMP/f'equation-{index}.png'
    mathtext.math_to_image('$'+text+'$',str(path),dpi=220,format='png',color='#17324d')
    w,h=ImageReader(str(path)).getSize();scale=min(72/220,WIDTH/w)
    return Image(str(path),width=w*scale,height=h*scale,hAlign='CENTER')

def table(lines):
    rows=[[c.strip() for c in l.strip().strip('|').split('|')] for l in lines]
    rows=[r for r in rows if not all(re.fullmatch(r'[: -]+',c or '-') for c in r)]
    n=len(rows[0]);factors={2:[.30,.70],3:[.24,.36,.40],4:[.19,.23,.27,.31],
                         6:[.08,.28,.14,.12,.18,.20]}.get(n,[1/n]*n)
    # The synthetic five-timepoint table has six equal numerical columns.
    if rows[0][0].startswith('Minutes'):factors=[.33]+[.67/(n-1)]*(n-1)
    cells=[[Paragraph(inline(c),styles['HeadCellMSE' if i==0 else 'CellMSE'])
            for c in row] for i,row in enumerate(rows)]
    t=LongTable(cells,colWidths=[WIDTH*f for f in factors],repeatRows=1,hAlign='LEFT')
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),NAVY),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),
        ('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,LIGHT]),
        ('LINEBELOW',(0,0),(-1,0),.4,NAVY),
        ('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#dce5eb'))]))
    return t

def build():
    story=[]
    story += [Spacer(1,32),Paragraph('MOTHER / COACH',ParagraphStyle('CoverTop',fontName='Bold',fontSize=14,textColor=TEAL,leading=20)),
              Spacer(1,24),Paragraph('Metabolic<br/>State Engine',ParagraphStyle('CoverTitle',fontName='Bold',fontSize=36,leading=43,textColor=NAVY)),
              Spacer(1,21),para('Repository audit, scientific architecture<br/>and a viable first vertical slice'),Spacer(1,13),
              para('MSE-001 v0.1.0  |  13 November 2026, Pacific/Guam','SmallMSE'),Spacer(1,25)]
    lead=LongTable([[para('**Architecture decision**<br/>Add a small, observable inference layer downstream of the existing evidence archive. Preserve working acquisition, version every interpretation, and keep unresolved biology explicit.')]],colWidths=[WIDTH])
    lead.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),.5,colors.HexColor('#bad4dd')),('LEFTPADDING',(0,0),(-1,-1),14),('RIGHTPADDING',(0,0),(-1,-1),14),('TOPPADDING',(0,0),(-1,-1),13),('BOTTOMPADDING',(0,0),(-1,-1),9)]))
    story += [lead,Spacer(1,24),para('**What is delivered**'),para('Pinned repository findings; hybrid state-space specification; conditional E1 graph and intervention contracts; offline HR/SDNN prototype; validation gates; installation and rollback documentation.'),Spacer(1,12),para('**Scope**'),para('Source inspection and synthetic software verification. No production deployment, iOS cutover, credential changes, treatment execution or automation-schedule changes.'),Spacer(1,12),para('All illustrative physiological values are synthetic. Model intervals remain explicitly uncalibrated.','SmallMSE'),PageBreak()]
    story += [para('Contents','H1MSE')]
    toc=TableOfContents();toc.levelStyles=[ParagraphStyle('TOC0',fontName='Body',fontSize=10.5,leading=20,textColor=NAVY,leftIndent=0,firstLineIndent=0)]
    story += [toc,Spacer(1,25),para('Evidence labels','H2MSE'),para('**Inspected:** read at a pinned source commit. **Reported:** described in project documentation or user observations. **Executed here:** performed in this isolated workspace. **Proposed:** new design. These labels do not establish live deployment or biological validity.'),para('The complete Markdown, source audits, machine contracts, prototype and verification records accompany this report. Repository references R01-R12 and scientific references S01-S21 are listed at the end.'),PageBreak()]
    text=SOURCE.read_text();text=text[text.index('# A. Repository audit'):]
    lines=text.splitlines();i=0;diagram_index=0;eq=0;first_section=True
    while i<len(lines):
        line=lines[i].strip()
        if not line:i+=1;continue
        if line.startswith('```'):
            lang=line[3:];block=[];i+=1
            while i<len(lines) and not lines[i].startswith('```'):block.append(lines[i]);i+=1
            i+=1
            if lang=='mermaid':
                story += [Spacer(1,8),diagram(diagram_index),Spacer(1,8)]
                diagram_index+=1
            else:story.append(Paragraph(html.escape('\n'.join(block)).replace('\n','<br/>'),styles['CodeMSE']))
            continue
        if line.startswith('$$') and line.endswith('$$'):
            eq+=1;story += [Spacer(1,6),equation(line[2:-2],eq),Spacer(1,12)];i+=1;continue
        if line.startswith('|'):
            block=[]
            while i<len(lines) and lines[i].strip().startswith('|'):block.append(lines[i]);i+=1
            story += [Spacer(1,4),table(block),Spacer(1,11)];continue
        heading=re.match(r'^(#{1,3})\s+(.*)$',line)
        if heading:
            level=len(heading[1]);label=heading[2]
            if level==1:
                if not first_section:story.append(PageBreak())
                first_section=False
            elif label.startswith(('E2. Learning from N-of-1',
                                   'G2. Concrete tests',
                                   'Primary scientific and official')):
                # Balance long sections and keep short tails off otherwise empty pages.
                story.append(PageBreak())
            p=para(label,'H1MSE' if level==1 else 'H2MSE' if level==2 else 'H3MSE')
            if level==1:p.toclevel=0
            story.append(p);i+=1;continue
        if line.startswith('- '):
            story.append(Paragraph(inline(line[2:]),styles['TextMSE'],bulletText='-'));i+=1;continue
        paragraph=[line];i+=1
        while i<len(lines) and lines[i].strip() and not re.match(r'^(#|\||```|\$\$|- )',lines[i].strip()):
            paragraph.append(lines[i].strip());i+=1
        story.append(para(' '.join(paragraph)))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    doc=Report(OUT);doc.multiBuild(story)
    print(OUT)

if __name__=='__main__':build()
