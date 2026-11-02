import os
import re
import uuid
import urllib.parse
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
import yt_dlp
import httpx

app = FastAPI(title="PureVoid Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

CACHE_DIR = "/tmp/purevoid_cache"
os.makedirs(CACHE_DIR, exist_ok=True)
COOKIES_FILE = os.path.join(os.path.dirname(__file__), "cookies.txt")

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|\n\r\t]', '', name).strip()
    return cleaned[:100] if len(cleaned) > 100 else (cleaned or "purevoid_video")

class URLRequest(BaseModel):
    playstore_url: str

class VoidRequest(BaseModel):
    url: str

@app.post("/api/download")
async def extract_apk(request: URLRequest):
    url = request.playstore_url
    if not re.search(r'play\.google\.com/store/apps/details\?id=', url):
        raise HTTPException(status_code=400, detail="Formato de URL inválido.")
    package_name = url.split("id=")[1].split("&")[0]
    versions = [
        {
            "id": 1,
            "type": "XAPK / Universal",
            "arch": "Todas",
            "target": "Recomendado para a maioria dos Celulares e Tablets modernos.",
            "download_link": f"https://d.apkpure.com/b/XAPK/{package_name}?version=latest"
        }
    ]
    return {
        "status": "sucesso",
        "package": package_name,
        "message": "Opções extraídas com sucesso.",
        "versions": versions
    }

@app.post("/api/void")
async def void_download(request: VoidRequest, req: Request):
    url = request.url.strip()
    download_url = None
    title = "purevoid_video"
    thumbnail = ""
    file_id = None

    # 1. TIKTOK (TikWM com fallback)
    if "tiktok.com" in url.lower():
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
            async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
                res = await client.get(f"https://www.tikwm.com/api/?url={url}")
                data = res.json()
                if data.get("code") == 0 and "data" in data:
                    title = data["data"].get("title", title)
                    thumbnail = data["data"].get("cover", "")
                    download_url = data["data"].get("play")
        except Exception:
            pass

    # 2. YOUTUBE / INSTAGRAM / OUTROS (yt-dlp via WARP SOCKS5)
    if not download_url:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'proxy': 'socks5://127.0.0.1:40000',
            'http_headers': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        }
        if os.path.exists(COOKIES_FILE):
            ydl_opts['cookiefile'] = COOKIES_FILE

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                title = info.get('title', title)
                thumbnail = info.get('thumbnail', '')
                
                # Procura primeiro formato progressivo MP4 (H.264 + AAC, 100% compativel com iOS)
                formats = info.get('formats', [])
                mp4_prog = [
                    f for f in formats 
                    if f.get('vcodec') and f.get('vcodec') != 'none' 
                    and f.get('acodec') and f.get('acodec') != 'none' 
                    and (f.get('ext') == 'mp4' or 'mp4' in (f.get('container') or ''))
                    and f.get('url')
                ]
                
                if mp4_prog:
                    download_url = mp4_prog[-1].get('url')
                else:
                    # Se não tem MP4 progressivo (ex: YouTube DASH com streams separados),
                    # baixamos e mesclamos em MP4 HD no servidor com ffmpeg
                    uid = str(uuid.uuid4())[:8]
                    clean = sanitize_filename(title)
                    out_path = f"{CACHE_DIR}/{uid}_{clean}.mp4"
                    merge_opts = {
                        'quiet': True,
                        'no_warnings': True,
                        'nocheckcertificate': True,
                        'proxy': 'socks5://127.0.0.1:40000',
                        'format': 'bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]/best',
                        'merge_output_format': 'mp4',
                        'outtmpl': out_path
                    }
                    if os.path.exists(COOKIES_FILE):
                        merge_opts['cookiefile'] = COOKIES_FILE

                    with yt_dlp.YoutubeDL(merge_opts) as merge_ydl:
                        merge_ydl.download([url])
                    
                    if os.path.exists(out_path):
                        file_id = f"{uid}_{clean}.mp4"
        except Exception as e:
            error_str = str(e)
            if "Sign in to confirm" in error_str:
                raise HTTPException(status_code=403, detail="O YouTube bloqueou a extração temporariamente.")
            raise HTTPException(status_code=400, detail=f"Erro ao extrair mídia: {error_str}")

    if not download_url and not file_id:
        raise HTTPException(status_code=400, detail="URL de download direto não encontrada.")

    clean_title = sanitize_filename(title)
    safe_title = urllib.parse.quote(clean_title)
    base_url = str(req.base_url).rstrip('/')
    if base_url.startswith("http://") and "localhost" not in base_url and "127.0.0.1" not in base_url:
        base_url = "https://" + base_url[7:]
    
    if file_id:
        final_link = f"{base_url}/api/file?file_id={urllib.parse.quote(file_id)}&title={safe_title}"
    else:
        safe_url = urllib.parse.quote(download_url, safe='')
        final_link = f"{base_url}/api/proxy?video_url={safe_url}&title={safe_title}"
    
    return {
        "status": "sucesso",
        "title": clean_title,
        "thumbnail": thumbnail,
        "download_link": final_link
    }

@app.get("/api/proxy")
@app.head("/api/proxy")
async def proxy_video(video_url: str, title: str = "video"):
    clean_title = sanitize_filename(title)
    ascii_title = clean_title.encode('ascii', 'ignore').decode('ascii').strip() or "video"
    encoded_title = urllib.parse.quote(clean_title)
    content_disposition = f'attachment; filename="{ascii_title}.mp4"; filename*=UTF-8\'\'{encoded_title}.mp4'

    proxy = "socks5://127.0.0.1:40000" if ("googlevideo.com" in video_url or "youtube" in video_url) else None
    client = httpx.AsyncClient(follow_redirects=True, proxy=proxy, timeout=60.0)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "*/*"
    }

    try:
        req = client.build_request("GET", video_url, headers=headers)
        resp = await client.send(req, stream=True)
    except Exception as e:
        await client.aclose()
        raise HTTPException(status_code=502, detail=f"Erro ao acessar vídeo upstream: {str(e)}")

    response_headers = {
        "Content-Disposition": content_disposition,
        "Content-Type": "video/mp4",
        "Accept-Ranges": "bytes"
    }
    if "content-length" in resp.headers:
        response_headers["Content-Length"] = resp.headers["content-length"]

    async def stream_generator():
        try:
            async for chunk in resp.aiter_bytes(chunk_size=65536):
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=resp.status_code,
        media_type="video/mp4",
        headers=response_headers
    )

@app.get("/api/file")
@app.head("/api/file")
async def serve_file(file_id: str, title: str = "video", background_tasks: BackgroundTasks = BackgroundTasks()):
    file_path = os.path.join(CACHE_DIR, os.path.basename(file_id))
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Arquivo expirado ou não encontrado.")

    clean_title = sanitize_filename(title)
    ascii_title = clean_title.encode('ascii', 'ignore').decode('ascii').strip() or "video"
    encoded_title = urllib.parse.quote(clean_title)
    content_disposition = f'attachment; filename="{ascii_title}.mp4"; filename*=UTF-8\'\'{encoded_title}.mp4'

    # Exclui o arquivo temporário após o envio completo
    background_tasks.add_task(os.remove, file_path)

    return FileResponse(file_path, media_type="video/mp4", headers={
        "Content-Disposition": content_disposition,
        "Content-Type": "video/mp4"
    })
