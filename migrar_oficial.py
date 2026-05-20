import os
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ==========================================
# CONFIGURACIÓN
# ==========================================
DEEZER_PLAYLIST_ID = "5414930062"
NUEVO_NOMBRE_PLAYLIST = "Samba"
SCOPES = ["https://www.googleapis.com/auth/youtube"]
# ==========================================

def obtener_canciones_deezer(playlist_id):
    url = f"https://api.deezer.com/playlist/{playlist_id}"
    response = requests.get(url)
    if response.status_code != 200:
        return []
    datos = response.json()
    canciones = []
    for track in datos.get('tracks', {}).get('data', []):
        nombre_cancion = track.get('title', '')
        nombre_artista = track.get('artist', {}).get('name', '')
        if nombre_cancion and nombre_artista:
            canciones.append(f"{nombre_cancion} {nombre_artista}")
    return canciones

def autenticar_youtube():
    creds = None
    # 1. Si existe un token viejo o roto, lo eliminamos para forzar el login limpio
    if os.path.exists("token.json"):
        try:
            os.remove("token.json")
        except:
            pass
    
    # 2. Forzamos la lectura directa de tus credenciales recién creadas
    print("   [INFO] Cargando componentes desde client_secret.json...")
    flow = InstalledAppFlow.from_client_secrets_file(
        "client_secret.json", 
        scopes=SCOPES
    )
    
    # 3. Abrimos el servidor local para capturar la respuesta de Google
    creds = flow.run_local_server(port=0)
    
    # 4. Guardamos el token válido
    with open("token.json", "w") as token:
        token.write(creds.to_json())
    
    return build("youtube", "v3", credentials=creds)

def buscar_y_añadir_canciones(youtube, playlist_id, canciones):
    print("4. Buscando y añadiendo canciones...")
    for i, cancion in enumerate(canciones, start=1):
        try:
            # Buscar el video/canción
            search_response = youtube.search().list(
                q=cancion,
                part="id,snippet",
                maxResults=1,
                type="video"
            ).execute()
            
            items = search_response.get("items", [])
            if items:
                video_id = items[0]["id"]["videoId"]
                # Añadir a la playlist
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id
                            }
                        }
                    }
                ).execute()
                print(f"   [{i}/{len(canciones)}] Encontrada y añadida: {cancion}")
            else:
                print(f"   [{i}/{len(canciones)}] [X] No encontrada: {cancion}")
        except Exception as e:
            print(f"   Error con '{cancion}': {e}")

def main():
    print("1. Obteniendo canciones de la lista de Deezer...")
    lista_canciones = obtener_canciones_deezer(DEEZER_PLAYLIST_ID)
    print(f"-> Se encontraron {len(lista_canciones)} canciones en Deezer.")
    
    print("2. Autenticando con Google de forma segura...")
    youtube = autenticar_youtube()
    
    print(f"3. Creando la nueva playlist '{NUEVO_NOMBRE_PLAYLIST}'...")
    try:
        playlist_response = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": NUEVO_NOMBRE_PLAYLIST,
                    "description": "Migrada desde Deezer."
                },
                "status": {
                    "privacyStatus": "private"
                }
            }
        ).execute()
        yt_playlist_id = playlist_response["id"]
        
        buscar_y_añadir_canciones(youtube, yt_playlist_id, lista_canciones)
        print("\n¡Migración completada con éxito!")
        
    except Exception as e:
        print(f"Error en la API de YouTube: {e}")

if __name__ == "__main__":
    main()