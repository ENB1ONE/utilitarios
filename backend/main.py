from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import re
import yt_dlp
import httpx
import urllib.parse

app = FastAPI(title="APK Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
    url = request.url
    download_url = None
    title = "Media Extraída (PureVoid)"
    thumbnail = ""

    # 1. TIKTOK (TikWM API com fallback)
    if "tiktok.com" in url.lower():
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
            async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
                res = await client.get(f"https://www.tikwm.com/api/?url={url}")
                data = res.json()
                if data.get("code") == 0 and "data" in data:
                    title = data["data"].get("title", title)
                    thumbnail = data["data"].get("cover", "")
                    download_url = data["data"].get("play")
        except Exception:
            pass

    # 2. YOUTUBE / OUTROS / FALLBACK (yt-dlp via WARP SOCKS5)
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
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if 'entries' in info:
                    info = info['entries'][0]
                title = info.get('title', title)
                download_url = info.get('url')
                if not download_url and 'formats' in info:
                    progressive = [f for f in info['formats'] if f.get('vcodec') != 'none' and f.get('acodec') != 'none']
                    if progressive:
                        download_url = progressive[-1].get('url')
                    elif info['formats']:
                        download_url = info['formats'][-1].get('url')
                thumbnail = info.get('thumbnail', '')
        except Exception as e:
            error_str = str(e)
            if "Sign in to confirm" in error_str:
                raise HTTPException(status_code=403, detail="O YouTube bloqueou a extração temporariamente.")
            raise HTTPException(status_code=400, detail=f"Erro ao extrair mídia: {error_str}")

    if not download_url:
        raise HTTPException(status_code=400, detail="URL de download direto não encontrada.")

    safe_url = urllib.parse.quote(download_url, safe='')
    base_url = str(req.base_url).rstrip('/')
    # Garante que use https caso venha por proxy reverso/tunnel
    if base_url.startswith("http://") and "localhost" not in base_url and "127.0.0.1" not in base_url:
        base_url = "https://" + base_url[7:]
    final_link = f"{base_url}/api/proxy?video_url={safe_url}"
    
    return {
        "status": "sucesso",
        "title": title,
        "thumbnail": thumbnail,
        "download_link": final_link
    }

@app.get("/api/proxy")
async def proxy_video(video_url: str):
    async def stream_generator():
        proxy = "socks5://127.0.0.1:40000" if ("googlevideo.com" in video_url or "youtube" in video_url) else None
        async with httpx.AsyncClient(follow_redirects=True, proxy=proxy, timeout=30.0) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
            try:
                async with client.stream("GET", video_url, headers=headers) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        yield chunk
            except Exception as e:
                yield f"Erro no proxy OCI (Video inacessivel): {str(e)}".encode()

    return StreamingResponse(stream_generator(), media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename=\"purevoid_media.mp4\""
    })
