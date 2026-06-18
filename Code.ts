const ARCHIVO_PROGRESO = "progreso_migracion.json";
// Apps script tiene un límite de ejecución de 6 minutos. Detendremos a los 5 mins.
const MAX_EXECUTION_TIME_MS = 5 * 60 * 1000; 

/** Función para ejecutar desde el editor o mediante triggers */
function main() {
  const startTime = Date.now();
  let progreso = cargarProgreso();
  
  // NOTA: Configura tu ID de Deezer aquí directamente para GAS
  const deezer_user_id = progreso.deezer_user_id || "AQUI_TU_ID_DE_DEEZER"; 
  progreso.deezer_user_id = deezer_user_id;
  guardarProgreso(progreso);
  
  console.log(`Obteniendo listas de reproducción del usuario ${deezer_user_id}...`);
  const playlists = obtenerPlaylistsUsuario(deezer_user_id);
  
  if (!progreso.playlists) progreso.playlists = {};

  for (let i = 0; i < playlists.length; i++) {
    const pl = playlists[i];
    console.log(`Procesando Playlist [${i + 1}/${playlists.length}]: ${pl.title}`);
    
    const cancionesDeezer = obtenerCancionesDeezer(pl.id);
    const yt_playlist_id = crearORecuperarPlaylistYoutube(pl, progreso);
    
    // Migrar canciones y verificar si nos quedamos sin tiempo o cuota
    const status = migrarCanciones(yt_playlist_id, pl.id, cancionesDeezer, progreso, startTime);
    
    if (status === 'STOP_QUOTA_OR_TIME') {
      console.log("Se alcanzó el límite de tiempo de ejecución o cuota. El progreso ha sido guardado. Ejecuta mañana.");
      return; // Detenemos la ejecución principal
    }
  }
  
  console.log("¡Todas las listas han sido procesadas!");
}

/** Carga el progreso desde Google Drive */
function cargarProgreso() {
  const files = DriveApp.getFilesByName(ARCHIVO_PROGRESO);
  if (files.hasNext()) {
    const file = files.next();
    try {
      return JSON.parse(file.getBlob().getDataAsString());
    } catch (e) {
      console.error("Error leyendo JSON, creando uno nuevo.");
    }
  }
  return { deezer_user_id: null, playlists: {} };
}

/** Guarda el progreso en Google Drive */
function guardarProgreso(progreso: any) {
  const files = DriveApp.getFilesByName(ARCHIVO_PROGRESO);
  const content = JSON.stringify(progreso, null, 2);
  if (files.hasNext()) {
    files.next().setContent(content);
  } else {
    DriveApp.createFile(ARCHIVO_PROGRESO, content, MimeType.PLAIN_TEXT);
  }
}

function obtenerPlaylistsUsuario(userId: string) {
  let playlists = [];
  let url = `https://api.deezer.com/user/${userId}/playlists`;
  
  while (url) {
    const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) break;
    
    const datos = JSON.parse(response.getContentText());
    for (const pl of (datos.data || [])) {
      playlists.push({ id: String(pl.id), title: pl.title });
    }
    url = datos.next;
  }
  return playlists;
}

function obtenerCancionesDeezer(playlistId: string) {
  let canciones = [];
  let url = `https://api.deezer.com/playlist/${playlistId}/tracks`;
  
  while (url) {
    const response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) break;
    
    const datos = JSON.parse(response.getContentText());
    for (const track of (datos.data || [])) {
      const trackId = String(track.id || '');
      const title = track.title || '';
      const artist = track.artist?.name || '';
      if (trackId && title && artist) {
        canciones.push({ id: trackId, query: `${title} ${artist}` });
      }
    }
    url = datos.next;
  }
  return canciones;
}

function crearORecuperarPlaylistYoutube(deezerPlaylist: any, progreso: any) {
  const plIdDeezer = deezerPlaylist.id;
  
  if (progreso.playlists[plIdDeezer]?.youtube_playlist_id) {
    return progreso.playlists[plIdDeezer].youtube_playlist_id;
  }
  
  try {
    const response = YouTube.Playlists!.insert({
      snippet: { title: deezerPlaylist.title, description: "Migrada desde Deezer." },
      status: { privacyStatus: "private" }
    }, "snippet,status");
    
    const ytId = response.id;
    progreso.playlists[plIdDeezer] = {
      name: deezerPlaylist.title,
      youtube_playlist_id: ytId,
      processed_track_ids: []
    };
    guardarProgreso(progreso);
    return ytId;
  } catch (e: any) {
    console.error(`Error al crear playlist YT: ${e.message}`);
    throw e;
  }
}

function migrarCanciones(ytPlaylistId: string, deezerPlaylistId: string, listaCanciones: any[], progreso: any, startTime: number) {
  const estadoPlaylist = progreso.playlists[deezerPlaylistId];
  const procesadas = new Set(estadoPlaylist.processed_track_ids || []);
  
  for (let i = 0; i < listaCanciones.length; i++) {
    // 1. Validar límite de tiempo (~5 minutos)
    if (Date.now() - startTime > MAX_EXECUTION_TIME_MS) {
      return 'STOP_QUOTA_OR_TIME';
    }
    
    const cancion = listaCanciones[i];
    if (procesadas.has(cancion.id)) continue;
      
    try {
      const searchResponse = YouTube.Search!.list("id,snippet", {
        q: cancion.query, maxResults: 1, type: ["video"]
      });
      
      if (searchResponse.items && searchResponse.items.length > 0) {
        const videoId = searchResponse.items[0].id?.videoId;
        YouTube.PlaylistItems!.insert({
          snippet: {
            playlistId: ytPlaylistId,
            resourceId: { kind: "youtube#video", videoId: videoId }
          }
        }, "snippet");
        console.log(`[OK] Añadida: ${cancion.query}`);
      } else {
        console.log(`[X] No encontrada: ${cancion.query}`);
      }
      
      estadoPlaylist.processed_track_ids.push(cancion.id);
      guardarProgreso(progreso);
      
    } catch (e: any) {
      const msg = e.message || String(e);
      if (msg.includes("quotaExceeded") || msg.includes("429") || msg.includes("403")) {
        return 'STOP_QUOTA_OR_TIME';
      } else {
        console.error(`Error con '${cancion.query}': ${msg}`);
      }
    }
  }
  return 'DONE';
}

/** Ejecuta esta función UNA SOLA VEZ desde el editor web para programar el script automáticamente cada noche */
function crearTriggerDiario() {
  ScriptApp.newTrigger("main").timeBased().everyDays(1).atHour(2).create();
}