import os
import sys
import json
import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ==========================================
# CONFIGURACIÓN
# ==========================================
SCOPES = ["https://www.googleapis.com/auth/youtube"]
ARCHIVO_PROGRESO = "progreso_migracion.json"
# ==========================================

def cargar_progreso():
    """Carga el archivo JSON de progreso local."""
    if os.path.exists(ARCHIVO_PROGRESO):
        with open(ARCHIVO_PROGRESO, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print("[!] Error leyendo progreso_migracion.json. Se creará uno nuevo.")
                pass
    return {"deezer_user_id": None, "playlists": {}}

def guardar_progreso(progreso):
    """Guarda el progreso en el archivo JSON local."""
    with open(ARCHIVO_PROGRESO, "w", encoding="utf-8") as f:
        json.dump(progreso, f, indent=4, ensure_ascii=False)

def obtener_playlists_usuario(user_id):
    """Obtiene todas las listas de reproducción de un usuario de Deezer (soporta paginación)."""
    playlists = []
    url = f"https://api.deezer.com/user/{user_id}/playlists"
    while url:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Error al obtener playlists de Deezer: {response.text}")
            break
        datos = response.json()
        for pl in datos.get('data', []):
            playlists.append({
                'id': str(pl['id']),
                'title': pl['title']
            })
        url = datos.get('next')  # Siguiente página
    return playlists

def obtener_canciones_deezer(playlist_id):
    """Obtiene todas las canciones de una playlist de Deezer (soporta paginación)."""
    canciones = []
    url = f"https://api.deezer.com/playlist/{playlist_id}/tracks"
    while url:
        response = requests.get(url)
        if response.status_code != 200:
            print(f"Error al obtener canciones de la playlist {playlist_id}: {response.text}")
            break
        datos = response.json()
        for track in datos.get('data', []):
            track_id = str(track.get('id', ''))
            nombre_cancion = track.get('title', '')
            nombre_artista = track.get('artist', {}).get('name', '')
            if track_id and nombre_cancion and nombre_artista:
                canciones.append({
                    'id': track_id,
                    'query': f"{nombre_cancion} {nombre_artista}"
                })
        url = datos.get('next')  # Siguiente página
    return canciones

def autenticar_youtube():
    """Autentica con la API de Google, reutilizando el token si es posible."""
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    
    # Si no hay credenciales válidas, pedir login o refrescar
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"[INFO] No se pudo refrescar el token ({e}). Iniciando nuevo login...")
                os.remove("token.json")
                flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
                creds = flow.run_local_server(port=0)
        else:
            print("   [INFO] Cargando componentes desde client_secret.json y solicitando permisos...")
            flow = InstalledAppFlow.from_client_secrets_file("client_secret.json", SCOPES)
            creds = flow.run_local_server(port=0)
        
        # Guardar token nuevo
        with open("token.json", "w") as token:
            token.write(creds.to_json())
            
    return build("youtube", "v3", credentials=creds)

def crear_o_recuperar_playlist_youtube(youtube, deezer_playlist, progreso):
    """Crea la lista en YT o devuelve su ID si ya había sido creada según el progreso."""
    pl_id_deezer = deezer_playlist['id']
    
    # Si ya la procesamos anteriormente, retornamos su ID
    if pl_id_deezer in progreso['playlists'] and progreso['playlists'][pl_id_deezer].get('youtube_playlist_id'):
        return progreso['playlists'][pl_id_deezer]['youtube_playlist_id']
    
    try:
        playlist_response = youtube.playlists().insert(
            part="snippet,status",
            body={
                "snippet": {
                    "title": deezer_playlist['title'],
                    "description": "Migrada desde Deezer."
                },
                "status": {
                    "privacyStatus": "private"
                }
            }
        ).execute()
        yt_playlist_id = playlist_response["id"]
        
        # Inicializar el progreso para esta playlist
        progreso['playlists'][pl_id_deezer] = {
            "name": deezer_playlist['title'],
            "youtube_playlist_id": yt_playlist_id,
            "processed_track_ids": []
        }
        guardar_progreso(progreso)
        return yt_playlist_id
        
    except HttpError as e:
        if e.resp.status in [403, 429]:
            print("\n[!] Límite de cuota de YouTube alcanzado al intentar crear la playlist.")
            print("Ejecuta el script de nuevo mañana.")
            sys.exit(0)
        else:
            print(f"Error al crear playlist en YouTube: {e}")
            raise e

def migrar_canciones(youtube, yt_playlist_id, deezer_playlist_id, lista_canciones, progreso):
    """Busca e inserta canciones de una en una, guardando el progreso por cada éxito/fallo."""
    estado_playlist = progreso['playlists'][deezer_playlist_id]
    procesadas = set(estado_playlist.get("processed_track_ids", []))
    
    total = len(lista_canciones)
    print(f"   * {total} canciones en Deezer. Ya procesadas: {len(procesadas)}. Restantes: {total - len(procesadas)}.")

    for i, cancion in enumerate(lista_canciones, start=1):
        track_id = cancion['id']
        query = cancion['query']
        
        if track_id in procesadas:
            # Saltamos para no gastar cuota
            continue
            
        try:
            # 1. Buscar en YouTube
            search_response = youtube.search().list(
                q=query,
                part="id,snippet",
                maxResults=1,
                type="video"
            ).execute()
            
            items = search_response.get("items", [])
            if items:
                video_id = items[0]["id"]["videoId"]
                # 2. Añadir a la playlist
                youtube.playlistItems().insert(
                    part="snippet",
                    body={
                        "snippet": {
                            "playlistId": yt_playlist_id,
                            "resourceId": {
                                "kind": "youtube#video",
                                "videoId": video_id
                            }
                        }
                    }
                ).execute()
                print(f"   [{i}/{total}] [OK] Añadida: {query}")
            else:
                print(f"   [{i}/{total}] [X] No encontrada en YT: {query}")
            
            # Registrar como procesada y guardar
            # Lo hacemos tanto si se encontró como si no, para no reintentar fallidas infinitamente
            estado_playlist["processed_track_ids"].append(track_id)
            guardar_progreso(progreso)
            
        except HttpError as e:
            if e.resp.status in [403, 429]:
                print(f"\n[!] Límite de cuota diario de YouTube alcanzado en la canción {i} ('{query}').")
                print("El progreso ha sido guardado. Vuelve a ejecutar este script mañana para continuar.")
                sys.exit(0)
            else:
                print(f"   [{i}/{total}] [Error API] con '{query}': {e}")
        except Exception as e:
            print(f"   [{i}/{total}] [Error inesperado] con '{query}': {e}")

def main():
    print("==============================================")
    print("   Migrador Persistente Deezer -> YT Music    ")
    print("==============================================")
    
    progreso = cargar_progreso()
    
    deezer_user_id = progreso.get("deezer_user_id")
    if not deezer_user_id:
        deezer_user_id = input("Por favor, introduce tu ID de usuario de Deezer (solo números): ").strip()
        progreso["deezer_user_id"] = deezer_user_id
        guardar_progreso(progreso)
        
    print("\n1. Autenticando con Google de forma segura...")
    youtube = autenticar_youtube()
    
    print(f"\n2. Obteniendo listas de reproducción del usuario {deezer_user_id}...")
    playlists = obtener_playlists_usuario(deezer_user_id)
    print(f"-> Se encontraron {len(playlists)} listas de reproducción en total.")
    
    if 'playlists' not in progreso:
        progreso['playlists'] = {}

    for index, pl in enumerate(playlists, start=1):
        print(f"\n----------------------------------------------")
        print(f"Playlist [{index}/{len(playlists)}]: {pl['title']}")
        
        # Evitar buscar canciones si la lista ya está completa según nuestro progreso
        canciones_deezer = obtener_canciones_deezer(pl['id'])
        
        yt_playlist_id = crear_o_recuperar_playlist_youtube(youtube, pl, progreso)
        
        migrar_canciones(youtube, yt_playlist_id, pl['id'], canciones_deezer, progreso)

    print("\n¡Todas las listas han sido procesadas o estaban actualizadas!")

if __name__ == "__main__":
    main()