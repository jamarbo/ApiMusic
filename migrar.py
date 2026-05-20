import requests
from ytmusicapi import YTMusic

# ==========================================
# CONFIGURACIÓN: Reemplaza con tus datos
# ==========================================
DEEZER_PLAYLIST_ID = "5414930062"  # Ej: "1234567890"
NUEVO_NOMBRE_PLAYLIST = "Samba"
# ==========================================

def obtener_canciones_deezer(playlist_id):
    url = f"https://api.deezer.com/playlist/{playlist_id}"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"Error al conectar con Deezer (Status: {response.status_code})")
        return []
    
    datos = response.json()
    if 'error' in datos:
        print(f"Error de la API de Deezer: {datos['error'].get('message')}")
        print("Asegúrate de que la playlist de Deezer sea PÚBLICA.")
        return []

    canciones = []
    tracks = datos.get('tracks', {}).get('data', [])
    
    for track in tracks:
        # Combinamos título y artista para una búsqueda precisa en YT Music
        nombre_cancion = track.get('title', '')
        nombre_artista = track.get('artist', {}).get('name', '')
        if nombre_cancion and nombre_artista:
            canciones.append(f"{nombre_cancion} {nombre_artista}")
            
    return canciones

def migrar_a_ytmusic():
    print("1. Conectando con YouTube Music usando tus credenciales...")
    try:
        # Cambiamos "browser.json" por "headers.txt" para leer las cabeceras crudas
        ytm = YTMusic("browser.json")    
    except Exception as e:
        print(f"Error al leer browser.json: {e}")
        return

    print("2. Obteniendo canciones de la lista de Deezer...")
    lista_canciones = obtener_canciones_deezer(DEEZER_PLAYLIST_ID)
    
    if not lista_canciones:
        print("No se encontraron canciones para migrar.")
        return

    print(f"-> Se encontraron {len(lista_canciones)} canciones en Deezer.")
    print(f"3. Creando la nueva playlist '{NUEVO_NOMBRE_PLAYLIST}' en tu cuenta...")
    
    try:
        yt_playlist_id = ytm.create_playlist(
            title=NUEVO_NOMBRE_PLAYLIST, 
            description="Migrada automáticamente desde Deezer vía script de Python."
        )
    except Exception as e:
        print(f"Error al crear la playlist en YouTube Music: {e}")
        return
    
    id_canciones_encontradas = []
    print("4. Buscando coincidencias en YouTube Music (esto puede tomar un momento)...")
    
    for i, cancion in enumerate(lista_canciones, start=1):
        try:
            # Buscamos filtrando solo por canciones oficiales para evitar videoclips largos
            resultados = ytm.search(cancion, filter="songs")
            if resultados:
                video_id = resultados[0]['videoId']
                id_canciones_encontradas.append(video_id)
                print(f"   [{i}/{len(lista_canciones)}] Encontrada: {cancion}")
            else:
                print(f"   [{i}/{len(lista_canciones)}] [X] No encontrada: {cancion}")
        except Exception as e:
            print(f"   Error buscando '{cancion}': {e}")

    if id_canciones_encontradas:
        print(f"5. Añadiendo {len(id_canciones_encontradas)} canciones a tu nueva playlist...")
        # Añadimos los IDs mapeados a la playlist de destino
        ytm.add_playlist_items(yt_playlist_id, id_canciones_encontradas)
        print("\n¡Proceso finalizado con éxito! Revisa tu aplicación de YouTube Music.")
    else:
        print("\nNo se pudo emparejar ninguna canción en el catálogo de destino.")

if __name__ == "__main__":
    migrar_a_ytmusic()