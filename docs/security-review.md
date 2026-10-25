# Revisión de seguridad — 2026-10-22

Actualización: las correcciones de SEC-01/02/03 ya están aplicadas al código.
Los hallazgos siguientes conservan la evidencia del estado anterior; sus números
de línea corresponden a ese estado. Véase `security-fixes.md` para los cambios,
las pruebas y las limitaciones de validación actuales.

Alcance: Dockerfile, catálogo e instalador ACP, init de permisos, lanzador Muse,
workflow y documentación de la revisión del 2026-10-22. Esta revisión no acredita
la seguridad de un despliegue: su Compose, red, montajes e identidad efectiva
del daemon deben inspeccionarse por separado.

## Hallazgos prioritarios

### SEC-01 — Alta: se aceptan binarios sin checksum fijado

Ubicación: `docker/paseo-acp.py`, líneas 40–43 y 135; inventario ACP.

Hay 14 distribuciones de arquitectura sin `sha256`, correspondientes a Cortex
Code, Corust, crow-cli, Cursor, Devin, Junie, Stakpak y VT Code. `download()`
permite instalarlas y solamente registra el hash después de descargarlas. Si el
artefacto servido por esa URL cambia, el build acepta contenido distinto sin
compararlo con el artefacto revisado. HTTPS protege el transporte, pero no fija
el contenido frente a un cambio del origen o de sus publicaciones.

Evidencia: una respuesta simulada con bytes arbitrarios y `expected=None` fue
aceptada por el instalador en un contenedor sin red. No se ejecutó ese contenido.

Corrección propuesta: exigir SHA-256 válido antes de descargar cada binario;
obtenerlo de publicaciones verificadas o calcular y revisar deliberadamente el
artefacto al actualizar el inventario. Si falta, detener la instalación o marcar
esa distribución como no disponible. Calcular el hash en cada build y aceptarlo
automáticamente no elimina el problema.

### SEC-02 — Alta condicionada: carrera de enlaces durante la reparación como root

Ubicación: `docker/paseo-agent-config-permissions.sh`, líneas 18–20 y 37–46.

`find ! -type l` comprueba el tipo antes de ejecutar `chown`/`chmod` por nombre.
Un escritor concurrente con acceso al home puede reemplazar un candidato por un
enlace después de esa comprobación. `chown` sigue entonces el enlace final y
modifica un archivo fuera del árbol previsto con los privilegios del init.
Comprobar únicamente `-L` sobre el último componente tampoco protege todos los
ancestros de rutas personalizadas.

Precondición: debe existir un escritor concurrente durante el arranque, por
ejemplo otro proceso o contenedor que comparta el volumen. La prueba no demuestra
un ataque remoto ni una fuga del contenedor al host.

Evidencia: en un contenedor sin red se instrumentó `chown` para reproducir el
intercalado exacto entre comprobación y uso. Un archivo temporal externo al home,
inicialmente propiedad de root, terminó con UID 1000. No se tocaron rutas del
servidor ni credenciales. La prueba existente de enlaces estáticos no cubre esta
carrera.

Corrección propuesta: recorrer desde directorios autorizados mediante
descriptores y operaciones que rechacen enlaces en cada componente, verificar
identidad/tipo/dispositivo y aplicar `fchown`/`fchmod` al descriptor verificado.
`chown -h` limita parte del problema, pero no sustituye la protección frente al
reemplazo de directorios ancestros. Evitar escritores concurrentes es una medida
operativa adicional, no una reparación completa del código.

### SEC-03 — Media: las dependencias transitivas cambian fuera de la revisión

Ubicación: `docker/paseo-acp.py`, líneas 91–97 y 123; instalación npm del Dockerfile.

El llamado `acp-catalog.lock.json` fija el paquete principal, pero no contiene el
grafo completo de dependencias. El instalador genera un nuevo package-lock desde
el registro en cada build y después ejecuta `npm ci`, incluidos scripts de
instalación. Las herramientas Python instaladas con `uv pip install` tampoco
usan un lockfile completo. Una nueva dependencia que satisfaga los rangos puede
incorporarse sin cambiar el inventario revisado. Esos scripts/build backends se
ejecutan con los permisos del build, actualmente root dentro del contenedor.

La verificación de integridad del paquete npm principal antes de ejecutar
scripts es una protección útil, pero no cubre versiones transitivas nuevas.
Hermes sí utiliza su lockfile upstream mediante `uv sync --frozen`.

Corrección propuesta: conservar locks completos revisados por proveedor y usar
`npm ci` directamente sobre ellos; para Python, fijar el grafo y los hashes de
artefactos. Separar las instalaciones de paquetes de los pasos privilegiados,
evitar credenciales durante el build y permitir scripts de instalación solo
cuando se haya revisado su necesidad. No desactivar todos los scripts sin
comprobar antes los proveedores que descargan binarios en postinstall.

## Límite de aislamiento entre agentes

Los directorios y virtualenvs separados aíslan dependencias, no permisos del
sistema operativo. Si un agente puede ejecutar código sin un sandbox que lo
impida, UID 1000 puede leer archivos `600` de ese mismo UID, incluidas credenciales
de otros proveedores bajo `/home/paseo`. Para una frontera de confianza entre
proveedores o proyectos hacen falta usuarios/contenedores separados, montajes
limitados y credenciales de alcance reducido. La compatibilidad con bubblewrap debe
validarse en cada despliegue según el SDD.

## Comprobaciones realizadas y límites

- Reproducción controlada de SEC-01 y SEC-02 en Docker Linux, sin red y con el
  proyecto montado solo para lectura. Solo se modificaron archivos temporales.
- Consulta a [OSV](https://osv.dev/) de 26 versiones directas npm/Python:
  cero paquetes con avisos devueltos en esa consulta. No incluye las dependencias
  transitivas, el sistema base, todos los binarios ni las dependencias de Hermes.
  No equivale a afirmar que la imagen está libre de vulnerabilidades.
- Búsqueda por patrones de tokens GitHub/OpenAI y claves privadas en los archivos
  actuales: sin coincidencias. No se escaneó todo el historial Git ni el servidor.
- Acciones de GitHub fijadas por commit, permisos del token de Actions limitados
  a lectura del contenido, configuraciones escritas con permisos privados y
  extracción de archivos con controles de rutas observados en el código.
- No existe una imagen completa validada de este cambio para generar un SBOM y
  realizar un escaneo de vulnerabilidades de todo el sistema resultante.

Los escenarios reproducidos tienen ahora pruebas de regresión y correcciones
aplicadas. La validación de imagen completa, despliegue y aislamiento entre
proveedores sigue siendo independiente de estas correcciones del código.
