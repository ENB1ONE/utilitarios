from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import re
import yt_dlp

app = FastAPI(title="APK Downloader API")

# Configuração de CORS
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
        raise HTTPException(status_code=400, detail="Formato de URL inválido. Use um link oficial da Play Store.")
    
    package_name = url.split("id=")[1].split("&")[0]
    
    versions = [
        {
            "id": 1,
            "type": "XAPK / Universal",
            "arch": "Todas",
            "target": "Recomendado para a maioria dos Celulares e Tablets modernos. Contém todos os recursos originais.",
            "download_link": f"https://d.apkpure.com/b/XAPK/{package_name}?version=latest"
        },
        {
            "id": 2,
            "type": "APK Normal",
            "arch": "arm64-v8a",
            "target": "Celulares de médio a alto padrão recentes (após 2017). Mais rápido e consome menos memória.",
            "download_link": f"https://d.apkpure.com/b/APK/{package_name}?version=latest&arch=arm64-v8a"
        },
        {
            "id": 3,
            "type": "APK Legado",
            "arch": "armeabi-v7a",
            "target": "Celulares muito antigos, TV Boxes, Emuladores ou Smartwatches de baixa performance.",
            "download_link": f"https://d.apkpure.com/b/APK/{package_name}?version=latest&arch=armeabi-v7a"
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
        'skip_download': True, # Nós só queremos a URL real
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Se for uma playlist, pega o primeiro
            if 'entries' in info:
                info = info['entries'][0]
            
            title = info.get('title', 'Media Extraída (PureVoid)')
            download_url = info.get('url')
            thumbnail = info.get('thumbnail', '')
            
            if not download_url:
                raise Exception("URL de download direto não encontrada.")
            
            return {
                "status": "sucesso",
                "title": title,
                "thumbnail": thumbnail,
                "download_link": download_url
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao extrair mídia: Não suportado ou privado. Detalhe: {str(e)}")
