import os
import asyncio
import shutil
import tempfile
import pathlib
import pandas as pd
import pypandoc
import fitz
from PIL import Image
import cairosvg
import json
import yaml
import toml
import shlex
from playwright.async_api import async_playwright

# The atomic engine pathways. Dijkstra will string these together instantly.
DIRECT_EDGES = {
    'docx': ['pdf', 'html', 'txt', 'md'],
    'doc': ['pdf', 'docx'],
    'pptx': ['pdf'],
    'rtf': ['pdf', 'docx', 'html', 'txt', 'md'],
    'odt': ['pdf', 'docx'],
    'txt': ['pdf', 'html', 'md', 'docx', 'json'],  # txt->json bridge connects Documents to Data!
    'html': ['pdf', 'md', 'txt', 'docx'],
    'md': ['html', 'txt', 'docx'],
    'epub': ['html', 'txt', 'md'],
    'pdf': ['html', 'txt'],
    'djvu': ['pdf'],
    'csv': ['pdf'],
    'xlsx': ['csv', 'pdf'],
    'svg': ['png', 'pdf'],
    'jpg': ['png', 'webp', 'pdf'],
    'png': ['jpg', 'webp', 'pdf'],
    'webp': ['jpg', 'png', 'pdf'],
    'gif': ['png', 'mp4'],
    'mp4': ['webm', 'gif', 'mp3'],
    'webm': ['mp4', 'gif', 'mp3'],
    'mp3': ['wav'],
    'wav': ['mp3'],
    'zip': ['7z', 'tar', 'gz'],
    'rar': ['zip', '7z', 'tar', 'gz'],
    '7z': ['zip', 'tar', 'gz'],
    'tar': ['zip', '7z', 'gz'],
    'gz': ['zip', '7z', 'tar'],
    'json': ['yaml', 'toml', 'xml', 'txt'],
    'yaml': ['json', 'toml', 'xml', 'txt'],
    'toml': ['json', 'yaml', 'xml', 'txt'],
    'xml': ['json', 'yaml', 'toml', 'txt']
}

def find_shortest_path(start, end):
    queue = [(start, [start])]
    visited = set()
    while queue:
        (node, path) = queue.pop(0)
        if node == end: return path
        if node not in visited:
            visited.add(node)
            for neighbor in DIRECT_EDGES.get(node, []):
                queue.append((neighbor, path + [neighbor]))
    return None

async def _run_process(*cmd, timeout=300):
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try: await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        try: proc.kill()
        except: pass
        raise Exception(f"Engine process timed out after {timeout} seconds.")
    if proc.returncode != 0 and cmd[0] not in ['libreoffice']:
        raise Exception(f"Engine failure with code {proc.returncode}.")

async def _run_ffmpeg(input_path: str, output_path: str, from_fmt: str, to_fmt: str, audio_opts: str, video_opts: str, custom_ffmpeg: str):
    cmd = ["ffmpeg", "-y", "-i", input_path]
    vf = []
    af = []
    
    if video_opts and from_fmt not in ['mp3', 'wav']:
        try:
            v_opts = json.loads(video_opts)
            if v_opts.get('resize'): vf.append(f"scale={v_opts['resize']}")
            if v_opts.get('crop'): vf.append(f"crop={v_opts['crop']}")
            if v_opts.get('filter') == 'grayscale': vf.append("format=gray")
            elif v_opts.get('filter') == 'sepia': vf.append("colorchannelmixer=.393:.769:.189:0:.349:.686:.168:0:.272:.534:.131")
            elif v_opts.get('filter') == 'invert': vf.append("negate")
        except: pass
        
    if audio_opts and from_fmt not in ['jpg', 'png', 'webp']:
        try:
            a_opts = json.loads(audio_opts)
            tempo = float(a_opts.get('tempo', 1.0))
            if tempo != 1.0: af.append(f"atempo={tempo}")
            
            reverb = float(a_opts.get('reverb', 0))
            if reverb > 0:
                decay = reverb / 100.0
                af.append(f"aecho=0.8:0.9:1000:{decay}")
                
            bass = float(a_opts.get('bass', 0))
            if bass != 0: af.append(f"bass=g={bass}")
        except: pass
        
    if vf: cmd.extend(["-vf", ",".join(vf)])
    if af: cmd.extend(["-af", ",".join(af)])
        
    if to_fmt in ['jpg', 'png', 'webp'] and from_fmt in ['gif', 'mp4', 'webm']:
        cmd.extend(["-vframes", "1"])
        
    if custom_ffmpeg:
        try:
            custom_args = shlex.split(custom_ffmpeg)
            bad_flags = {'-i', '-f', '-d', '-y', '-n'}
            for arg in custom_args:
                # Basic injection filter blocking paths
                if '/' in arg or '\\' in arg or '..' in arg: continue
                if arg in bad_flags: continue
                cmd.append(arg)
        except: pass

    cmd.append(output_path)
    
    proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    try: await asyncio.wait_for(proc.communicate(), timeout=600)
    except asyncio.TimeoutError:
        try: proc.kill()
        except: pass
        raise Exception("FFmpeg processing timed out.")
    if proc.returncode != 0:
        raise Exception("FFmpeg engine failure. Verify your custom FFmpeg flags and media constraints.")

async def convert_document(input_path: str, output_path: str, from_fmt: str, to_fmt: str, audio_opts: str = None, video_opts: str = None, custom_ffmpeg: str = None):
    path = find_shortest_path(from_fmt, to_fmt)
    if not path: raise Exception(f"No conversion path found from {from_fmt} to {to_fmt}")

    current_input = input_path
    temp_files = []
    task_dir = os.path.dirname(output_path)

    try:
        for i in range(len(path) - 1):
            curr_fmt = path[i]
            next_fmt = path[i+1]
            if i == len(path) - 2: current_output = output_path
            else:
                fd, temp_path = tempfile.mkstemp(suffix=f".{next_fmt}", dir=task_dir)
                os.close(fd)
                temp_files.append(temp_path)
                current_output = temp_path
                
            if i == len(path) - 2:
                await _direct_convert(current_input, current_output, curr_fmt, next_fmt, audio_opts, video_opts, custom_ffmpeg)
            else:
                await _direct_convert(current_input, current_output, curr_fmt, next_fmt)
                
            current_input = current_output
            
            if not os.path.exists(current_output) or os.path.getsize(current_output) == 0:
                raise Exception(f"Intermediate conversion failed at {curr_fmt} -> {next_fmt}")
    finally:
        for f in temp_files:
            if os.path.exists(f): os.remove(f)

async def _direct_convert(input_path: str, output_path: str, from_fmt: str, to_fmt: str, audio_opts: str = None, video_opts: str = None, custom_ffmpeg: str = None):
    # 0. Data Formats (JSON, YAML, TOML, XML) & The TXT Bridge
    DATA_FMTS = ['json', 'yaml', 'toml', 'xml']
    if (from_fmt in DATA_FMTS and to_fmt in DATA_FMTS + ['txt']) or (from_fmt == 'txt' and to_fmt in DATA_FMTS):
        
        if to_fmt == 'txt':
            shutil.copy(input_path, output_path)
            return
            
        if from_fmt == 'txt':
            with open(input_path, 'r', encoding='utf-8') as f:
                data = {"root": {"text_content": f.read()}}
        else:
            with open(input_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if from_fmt == 'json': data = json.loads(content)
                elif from_fmt == 'yaml': data = yaml.safe_load(content)
                elif from_fmt == 'toml': data = toml.loads(content)
                elif from_fmt == 'xml': 
                    import xmltodict
                    data = xmltodict.parse(content)
            
        with open(output_path, 'w', encoding='utf-8') as f:
            if to_fmt == 'json': json.dump(data, f, indent=4)
            elif to_fmt == 'yaml': yaml.dump(data, f, default_flow_style=False)
            elif to_fmt == 'toml': toml.dump(data, f)
            elif to_fmt == 'xml':
                import xmltodict
                if not isinstance(data, dict) or len(data) != 1:
                    data = {'root': data}
                f.write(xmltodict.unparse(data, pretty=True))
        return
    
    # 1. Playwright
    if from_fmt == 'html' and to_fmt == 'pdf':
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page()
            file_uri = pathlib.Path(input_path).resolve().as_uri()
            await page.goto(file_uri, wait_until="load")
            
            await page.add_style_tag(content="""
                body {
                    max-width: none !important;
                    padding: 0 !important;
                    margin: 0 !important;
                }
                body > *:first-child {
                    margin-top: 0 !important;
                }
            """)
            await page.pdf(
                path=output_path, 
                format="A4", 
                print_background=True, 
                margin={"top": "1in", "right": "1in", "bottom": "1in", "left": "1in"}
            )
            await browser.close()
        return

    # 2. PyMuPDF
    if from_fmt == 'pdf' and to_fmt in ['html', 'txt']:
        doc = fitz.open(input_path)
        if to_fmt == 'txt':
            with open(output_path, "w", encoding="utf-8") as f:
                f.write("\n".join([page.get_text() for page in doc]))
        else:
            html_content = "<!DOCTYPE html><html><body style='background:#f0f0f0; margin:0; padding:20px;'>"
            for page in doc: html_content += f"<div style='background:white; margin:0 auto 20px auto; position:relative; width:{page.rect.width}px; height:{page.rect.height}px; overflow:hidden;'>{page.get_text('html')}</div>"
            html_content += "</body></html>"
            with open(output_path, "w", encoding="utf-8") as f: f.write(html_content)
        return

    # 3. LibreOffice
    if to_fmt in ['pdf', 'docx'] and from_fmt in ['doc', 'docx', 'rtf', 'odt', 'txt', 'csv', 'xlsx', 'pptx']:
        outdir = os.path.dirname(output_path)
        cmd = ["libreoffice", "--headless", "--nologo", "--nofirststartwizard", "--convert-to", to_fmt, "--outdir", outdir, input_path]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        try: await asyncio.wait_for(proc.communicate(), timeout=300)
        except asyncio.TimeoutError:
            try: proc.kill()
            except: pass
        base_name = os.path.basename(input_path).rsplit('.', 1)[0]
        lo_out = os.path.join(outdir, f"{base_name}.{to_fmt}")
        if os.path.exists(lo_out) and lo_out != output_path: os.rename(lo_out, output_path)
        return

    # 4. DDJVU
    if from_fmt == 'djvu' and to_fmt == 'pdf':
        await _run_process("ddjvu", "-format=pdf", input_path, output_path, timeout=400)
        return

    # 5. FFmpeg (Audio/Video/Image Hijack for Custom Options)
    has_ffmpeg_opts = bool(audio_opts or video_opts or custom_ffmpeg)
    FFMPEG_MEDIA = ['mp4', 'webm', 'mp3', 'wav', 'gif']
    IMAGE_MEDIA = ['jpg', 'png', 'webp']
    
    if has_ffmpeg_opts and from_fmt in FFMPEG_MEDIA + IMAGE_MEDIA and to_fmt in FFMPEG_MEDIA + IMAGE_MEDIA:
        if to_fmt == 'mp3' and from_fmt in ['mp4', 'webm']:
            proc = await asyncio.create_subprocess_exec("ffprobe", "-i", input_path, "-show_streams", "-select_streams", "a", "-loglevel", "error", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            if not stdout.strip(): raise Exception("No audio track found in the video file.")
        await _run_ffmpeg(input_path, output_path, from_fmt, to_fmt, audio_opts, video_opts, custom_ffmpeg)
        return

    # 5. FFmpeg (Standard Fallback)
    if from_fmt in FFMPEG_MEDIA and to_fmt in FFMPEG_MEDIA:
        if to_fmt == 'mp3' and from_fmt in ['mp4', 'webm']:
            proc = await asyncio.create_subprocess_exec("ffprobe", "-i", input_path, "-show_streams", "-select_streams", "a", "-loglevel", "error", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            stdout, _ = await proc.communicate()
            if not stdout.strip(): raise Exception("No audio track found in the video file.")
        await _run_process("ffmpeg", "-y", "-i", input_path, output_path, timeout=600)
        return
    
    # 6. Pandoc
    PANDOC_IN = {'md': 'markdown', 'txt': 'markdown', 'html': 'html', 'docx': 'docx', 'rtf': 'rtf', 'epub': 'epub', 'odt': 'odt'}
    PANDOC_OUT = {'md': 'markdown', 'txt': 'plain', 'html': 'html', 'docx': 'docx', 'rtf': 'rtf', 'epub': 'epub', 'odt': 'odt'}
    if from_fmt in PANDOC_IN and to_fmt in PANDOC_OUT:
        if from_fmt == 'txt' and to_fmt == 'md':
            shutil.copy(input_path, output_path)
            return
        extra_args = ['--standalone', '--metadata', 'pagetitle=Document'] if to_fmt == 'html' else []
        pypandoc.convert_file(input_path, PANDOC_OUT[to_fmt], format=PANDOC_IN[from_fmt], outputfile=output_path, extra_args=extra_args)
        return

    # 7. Spreadsheets (Pandas)
    if from_fmt == 'csv' and to_fmt == 'xlsx':
        pd.read_csv(input_path).to_excel(output_path, index=False)
        return
    if from_fmt == 'xlsx' and to_fmt == 'csv':
        pd.read_excel(input_path).to_csv(output_path, index=False)
        return

    # 8. Images (Pillow / CairoSVG) (Bypassed if FFmpeg Options are active)
    if from_fmt == 'svg':
        if to_fmt == 'png': cairosvg.svg2png(url=input_path, write_to=output_path)
        elif to_fmt == 'pdf': cairosvg.svg2pdf(url=input_path, write_to=output_path)
        return
    if from_fmt in ['jpg', 'png', 'webp', 'gif'] and to_fmt in ['jpg', 'png', 'webp', 'pdf']:
        with Image.open(input_path) as img:
            if img.mode in ("RGBA", "LA", "P") and to_fmt in ["jpg", "pdf"]:
                img = img.convert("RGBA")
                bg = Image.new("RGB", img.size, (255, 255, 255))
                bg.paste(img, mask=img)
                img = bg
            elif img.mode != "RGB" and to_fmt in ["jpg", "pdf"]: img = img.convert("RGB")
            if to_fmt == "pdf": img.save(output_path, "PDF", resolution=100.0)
            else: img.save(output_path)
        return

    # 9. Archives
    if from_fmt in ['zip', 'rar', '7z', 'tar', 'gz'] and to_fmt in ['zip', '7z', 'tar', 'gz']:
        with tempfile.TemporaryDirectory() as tmpdir:
            await _run_process("7z", "x", input_path, f"-o{tmpdir}", "-y", timeout=300)
            base_out = output_path.replace('.zip', '').replace('.tar', '').replace('.gz', '').replace('.7z', '')
            if to_fmt == 'zip': shutil.make_archive(base_out, 'zip', tmpdir)
            elif to_fmt == 'tar': shutil.make_archive(base_out, 'tar', tmpdir)
            elif to_fmt == 'gz': shutil.make_archive(base_out, 'gztar', tmpdir)
            elif to_fmt == '7z': await _run_process("7z", "a", output_path, f"{tmpdir}/*", timeout=300)
        return

    raise Exception(f"Backend routing error: Direct execution missing for atomic hop {from_fmt}->{to_fmt}")