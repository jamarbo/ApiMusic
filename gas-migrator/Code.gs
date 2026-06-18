const ARCHIVO_PROGRESO = "progreso_migracion.json";
// Apps script tiene un límite de ejecución de 6 minutos. Detendremos a los 5 mins.
const MAX_EXECUTION_TIME_MS = 5 * 60 * 1000; 

/** Función para ejecutar desde el editor o mediante triggers */
function main() {
  const startTime = Date.now();
  let progreso = cargarProgreso();
  
  // NOTA: Configura tu ID de Deezer aquí directamente para GAS
  const deezer_user_id = progreso.deezer_user_id || "8920406"; 
  progreso.deezer_user_id = deezer_user_id;
  guardarProgreso(progreso);
  
  console.log(`Obteniendo listas de reproducción del usuario ${deezer_user_id}...`);
  const playlists = obtenerPlaylistsUsuario(deezer_user_id);
  
  if (!progreso.playlists) progreso.playlists = {};

  for (var i = 0; i < playlists.length; i++) {
    var pl = playlists[i];
    console.log(`Procesando Playlist [${i + 1}/${playlists.length}]: ${pl.title}`);
    
    var cancionesDeezer = obtenerCancionesDeezer(pl.id);
    var yt_playlist_id = crearORecuperarPlaylistYoutube(pl, progreso);
    
    // Migrar canciones y verificar si nos quedamos sin tiempo o cuota
    var status = migrarCanciones(yt_playlist_id, pl.id, cancionesDeezer, progreso, startTime);
    
    if (status === 'STOP_QUOTA_OR_TIME') {
      console.log("Se alcanzó el límite de tiempo de ejecución o cuota. El progreso ha sido guardado. Ejecuta mañana.");
      return; // Detenemos la ejecución principal
    }
  }
  
  console.log("¡Todas las listas han sido procesadas!");
}

/** Carga el progreso desde Google Drive */
function cargarProgreso() {
  var files = DriveApp.getFilesByName(ARCHIVO_PROGRESO);
  if (files.hasNext()) {
    var file = files.next();
    try {
      return JSON.parse(file.getBlob().getDataAsString());
    } catch (e) {
      console.error("Error leyendo JSON, creando uno nuevo.");
    }
  }
  return { deezer_user_id: null, playlists: {} };
}

/** Guarda el progreso en Google Drive */
function guardarProgreso(progreso) {
  var files = DriveApp.getFilesByName(ARCHIVO_PROGRESO);
  var content = JSON.stringify(progreso, null, 2);
  if (files.hasNext()) {
    files.next().setContent(content);
  } else {
    DriveApp.createFile(ARCHIVO_PROGRESO, content, MimeType.PLAIN_TEXT);
  }
}

function obtenerPlaylistsUsuario(userId) {
  var playlists = [];
  var url = "https://api.deezer.com/user/" + userId + "/playlists";
  
  while (url) {
    var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) break;
    
    var datos = JSON.parse(response.getContentText());
    var dataArr = datos.data || [];
    for (var idx = 0; idx < dataArr.length; idx++) {
      var pl = dataArr[idx];
      playlists.push({ id: String(pl.id), title: pl.title });
    }
    url = datos.next;
  }
  return playlists;
}

function obtenerCancionesDeezer(playlistId) {
  var canciones = [];
  var url = "https://api.deezer.com/playlist/" + playlistId + "/tracks";
  
  while (url) {
    var response = UrlFetchApp.fetch(url, { muteHttpExceptions: true });
    if (response.getResponseCode() !== 200) break;
    
    var datos = JSON.parse(response.getContentText());
    var dataArr = datos.data || [];
    for (var i = 0; i < dataArr.length; i++) {
      var track = dataArr[i];
      var trackId = String(track.id || '');
      var title = track.title || '';
      var artist = (track.artist && track.artist.name) || '';
      if (trackId && title && artist) {
        canciones.push({ id: trackId, query: title + ' ' + artist });
      }
    }
    url = datos.next;
  }
  return canciones;
}

function crearORecuperarPlaylistYoutube(deezerPlaylist, progreso) {
  var plIdDeezer = deezerPlaylist.id;
  
  if (progreso.playlists && progreso.playlists[plIdDeezer] && progreso.playlists[plIdDeezer].youtube_playlist_id) {
    return progreso.playlists[plIdDeezer].youtube_playlist_id;
  }
  
  try {
    var response = YouTube.Playlists.insert({
      snippet: { title: deezerPlaylist.title, description: "Migrada desde Deezer." },
      status: { privacyStatus: "private" }
    }, "snippet,status");
    
    var ytId = response.id;
    if (!progreso.playlists) progreso.playlists = {};
    progreso.playlists[plIdDeezer] = {
      name: deezerPlaylist.title,
      youtube_playlist_id: ytId,
      processed_track_ids: []
    };
    guardarProgreso(progreso);
    return ytId;
  } catch (e) {
    console.error("Error al crear playlist YT: " + (e.message || e));
    throw e;
  }
}

function migrarCanciones(ytPlaylistId, deezerPlaylistId, listaCanciones, progreso, startTime) {
  var estadoPlaylist = progreso.playlists[deezerPlaylistId] || { processed_track_ids: [] };
  var procesadas = {};
  var processedArr = estadoPlaylist.processed_track_ids || [];
  for (var j = 0; j < processedArr.length; j++) procesadas[processedArr[j]] = true;
  
  for (var i = 0; i < listaCanciones.length; i++) {
    // 1. Validar límite de tiempo (~5 minutos)
    if (Date.now() - startTime > MAX_EXECUTION_TIME_MS) {
      return 'STOP_QUOTA_OR_TIME';
    } 
    
    var cancion = listaCanciones[i];
    if (procesadas[cancion.id]) continue;
      
    try {
      var searchResponse = YouTube.Search.list("id,snippet", {
        q: cancion.query, maxResults: 1, type: ["video"]
      });
      
      if (searchResponse.items && searchResponse.items.length > 0) {
        var videoId = (searchResponse.items[0].id && searchResponse.items[0].id.videoId) || null;
        if (videoId) {
          YouTube.PlaylistItems.insert({
            snippet: {
              playlistId: ytPlaylistId,
              resourceId: { kind: "youtube#video", videoId: videoId }
            }
          }, "snippet");
          console.log("[OK] Añadida: " + cancion.query);
        } else {
          console.log("[X] No encontrada (sin videoId): " + cancion.query);
        }
      } else {
        console.log("[X] No encontrada: " + cancion.query);
      }
      
      estadoPlaylist.processed_track_ids = estadoPlaylist.processed_track_ids || [];
      estadoPlaylist.processed_track_ids.push(cancion.id);
      progreso.playlists[deezerPlaylistId] = estadoPlaylist;
      guardarProgreso(progreso);
      
    } catch (e) {
      // Pasamos el mensaje a minúsculas para atrapar "Quota exceeded" o "quotaExceeded"
      var msg = (e.message || String(e)).toLowerCase();
      
      // Distinguir entre error de cuota y error de permisos (ambos pueden ser 403)
      if (msg.indexOf("quota exceeded") !== -1 || msg.indexOf("quotaexceeded") !== -1 || msg.indexOf("429") !== -1) {
        console.log("Se alcanzó el límite de cuota de YouTube. El progreso ha sido guardado. Ejecuta mañana.");
        return 'STOP_QUOTA_OR_TIME';
      } else if (msg.indexOf("403") !== -1) {
        console.error("Error de PERMISOS (403) con '" + cancion.query + "': " + (e.message || String(e)));
        console.error("SOLUCIÓN: Asegúrate de que el 'Servicio Avanzado de YouTube' está habilitado en el editor y vuelve a ejecutar la función para re-autorizar los permisos.");
        return 'STOP_QUOTA_OR_TIME'; // Detenemos la ejecución para que el usuario lo arregle
      } else {
        console.error("Error inesperado con '" + cancion.query + "': " + (e.message || String(e)));
      }
    }
  }
  return 'DONE';
}

/** Ejecuta esta función UNA SOLA VEZ desde el editor web para programar el script automáticamente cada noche */
function crearTriggerDiario() {
  ScriptApp.newTrigger("main").timeBased().everyDays(1).atHour(6).create();
}
