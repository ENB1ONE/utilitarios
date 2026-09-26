from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
import re
import yt_dlp
import requests
import urllib.parse

app = FastAPI(title="APK Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://enb1one.github.io"],
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
async def void_download(request: VoidRequest):
    url = request.url
    
    ydl_opts = {
        'format': 'best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'nocheckcertificate': True,
        'extractor_args': {
            'youtube': ['player_client=android', 'player_skip=webpage,configs']
        },
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            if 'entries' in info:
                info = info['entries'][0]
            
            title = info.get('title', 'Media Extraída (PureVoid)')
            download_url = info.get('url')
            thumbnail = info.get('thumbnail', '')
            
            if not download_url:
                raise Exception("URL de download direto não encontrada.")
            
            # Encoda a URL do YouTube para passar para o nosso proxy
            safe_url = urllib.parse.quote(download_url, safe='')
            proxy_link = f"https://twist-associate-mazda-mostly.trycloudflare.com/api/proxy?video_url={safe_url}"
            
            return {
                "status": "sucesso",
                "title": title,
                "thumbnail": thumbnail,
                "download_link": proxy_link
            }
    except Exception as e:
        error_str = str(e)
        if "Sign in to confirm" in error_str:
            raise HTTPException(status_code=403, detail="O YouTube bloqueou a extração. Tente outro link.")
        raise HTTPException(status_code=400, detail=f"Erro ao extrair mídia: {error_str}")

@app.get("/api/proxy")
def proxy_video(video_url: str):
    # Streaming direto da nuvem para o cliente (em memória, sem salvar no HD)
    def iterfile():
        with requests.get(video_url, stream=True, headers={"User-Agent": "Mozilla/5.0"}) as r:
            r.raise_for_status()
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    yield chunk

    return StreamingResponse(iterfile(), media_type="video/mp4", headers={
        "Content-Disposition": "attachment; filename=\"purevoid_media.mp4\""
    })
