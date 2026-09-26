from fastapi import FastAPI, HTTPException
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
    download_url = None
    title = "Media Extraída (PureVoid)"
    thumbnail = ""

    # 1. TIKTOK (TikWM API para burlar IP-Lock da Oracle)
    if "tiktok.com" in url.lower():
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(f"https://www.tikwm.com/api/?url={url}")
                data = res.json()
                if data.get("code") == 0 and "data" in data:
                    title = data["data"].get("title", title)
                    thumbnail = data["data"].get("cover", "")
                    download_url = data["data"].get("play")
                else:
                    raise Exception("A API do TikTok retornou erro.")
        except Exception as e:
            raise HTTPException(status_code=400, detail="O TikTok bloqueou a extração desse vídeo.")

    # 2. YOUTUBE / OUTROS (yt-dlp)
    else:
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
                title = info.get('title', title)
                download_url = info.get('url')
                thumbnail = info.get('thumbnail', '')
        except Exception as e:
            error_str = str(e)
            if "Sign in to confirm" in error_str:
                raise HTTPException(status_code=403, detail="O YouTube bloqueou a extração. Tente outro link.")
            raise HTTPException(status_code=400, detail=f"Erro ao extrair mídia: {error_str}")

    if not download_url:
        raise HTTPException(status_code=400, detail="URL de download direto não encontrada.")

    # OBRIGATÓRIO: Passar TODOS os links pelo Túnel Proxy OCI.
    # Motivo: Se não passarmos pelo proxy, o link da CDN (TikTok/Insta) abrirá 
    # o vídeo no Player do Navegador. O Proxy injeta 'Content-Disposition: attachment',
    # forçando o celular/PC a INICIAR O DOWNLOAD IMEDIATAMENTE (salvar na galeria).
    safe_url = urllib.parse.quote(download_url, safe='')
    final_link = f"https://twist-associate-mazda-mostly.trycloudflare.com/api/proxy?video_url={safe_url}"
    
    return {
        "status": "sucesso",
        "title": title,
        "thumbnail": thumbnail,
        "download_link": final_link
    }

@app.get("/api/proxy")
async def proxy_video(video_url: str):
    async def stream_generator():
        async with httpx.AsyncClient(follow_redirects=True) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "*/*"
            }
            try:
                async with client.stream("GET", video_url, headers=headers) as response:
                    response.raise_for_status()
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
            except httpx.HTTPStatusError as e:
                yield f"Erro no proxy OCI (Video inacessivel): {str(e)}".encode()

    return StreamingResponse(stream_generator(), media_type="application/octet-stream", headers={
        "Content-Disposition": "attachment; filename=\"purevoid_media.mp4\""
    })
