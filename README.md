# Migrador de Deezer a YouTube Music

Este script en Python te permite migrar automáticamente todas tus listas de reproducción de Deezer a YouTube Music utilizando la API oficial de Google y la API pública de Deezer.

## Características
- **Migración Completa:** Escanea todas las listas de tu perfil de Deezer.
- **Evita Duplicados y Ahorra Cuota:** Mantiene un registro local (`progreso_migracion.json`) de las canciones ya procesadas. Si se detiene por algún error o por el límite de la cuota gratuita de Google, puedes volver a ejecutarlo al día siguiente y continuará desde donde se quedó.
- **Manejo Automático de Errores:** Captura los errores 403 (Quota Exceeded) de YouTube y guarda el progreso de forma segura.
- **Autenticación Persistente:** Reutiliza el token de Google para no tener que iniciar sesión en cada ejecución.

## Requisitos Previos

1. **Python 3.x** instalado en tu sistema.
2. **Credenciales de Google API:**
   - Ve a [Google Cloud Console](https://console.cloud.google.com/).
   - Crea un nuevo proyecto y habilita la **YouTube Data API v3**.
   - Configura la Pantalla de Consentimiento de OAuth (añade tu correo como usuario de prueba si está en modo prueba).
   - Crea Credenciales de tipo **ID de cliente de OAuth** (Aplicación de Escritorio).
   - Descarga el archivo JSON de las credenciales, renómbralo a `client_secret.json` y guárdalo en la misma carpeta que este script.

## Instalación

1. Clona este repositorio o descarga los archivos.
2. Abre una terminal en la carpeta del proyecto.
3. Instala las dependencias necesarias ejecutando:

```bash
pip install requests google-auth-oauthlib google-api-python-client
```

## Uso

1. Asegúrate de tener el archivo `client_secret.json` en la raíz del proyecto.
2. Ejecuta el script:

```bash
python migrar_oficial.py
```

3. **Primera ejecución:**
   - El script te pedirá tu **ID de usuario de Deezer** (puedes encontrarlo en la URL de tu perfil de Deezer, son solo números).
   - Se abrirá una ventana en tu navegador para que inicies sesión con tu cuenta de Google y des permisos a la aplicación para administrar tu YouTube.

4. **Límites de Cuota (Importante):**
   - La API gratuita de YouTube tiene una cuota diaria de 10,000 unidades. Buscar y añadir canciones consume cuota rápidamente.
   - Si alcanzas el límite, el script te avisará y se cerrará de forma segura.
   - **No borres el archivo `progreso_migracion.json`**. Al día siguiente, vuelve a ejecutar el script y continuará la migración automáticamente donde se detuvo.

## Archivos Ignorados
Asegúrate de no compartir nunca públicamente tus credenciales. El archivo `.gitignore` ya está configurado para excluir `client_secret.json`, `token.json` y `progreso_migracion.json`.
