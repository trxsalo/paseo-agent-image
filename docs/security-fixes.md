# Correcciones de seguridad — 2026-10-22

- **SEC-01:** el instalador rechaza un checksum ausente/mal formado antes de
  abrir la red, y rechaza cualquier discrepancia. Se añadieron ocho digests
  oficiales de assets de GitHub al inventario. Las seis distribuciones de
  Cortex Code, Cursor y Devin que siguen sin hash quedan como no disponibles,
  sin descargar ni ejecutar sus artefactos.
- **SEC-02:** init usa `openat` vía `dir_fd`, `O_NOFOLLOW`, `fstat`, `fchown` y
  `fchmod` sobre descriptores verificados. Rechaza ancestros simbólicos, omite
  hardlinks y compara dispositivo e identidad de montaje de `/proc/self/fdinfo`
  antes de modificar cada inode. Solo autoriza el home, que queda con modo 700.
  El helper se ejecuta con Python aislado (`-I -S`) para ignorar hooks del
  workspace/PYTHONPATH. El entrypoint conserva Tini y baja con gosu antes de
  delegar a la preparación de directorios upstream. Falla si el helper o
  la verificación inicial no funcionan. Las rutas personalizadas externas y
  los montajes anidados requieren preparación explícita del administrador.
- **SEC-03:** se incluyen 24 package-lock completos (cinco CLIs nativas,
  dieciocho ACP npm y el runtime Amp), dos grafos Python con hashes y el lock
  de uv. Cada referencia se protege además con el hash del archivo de lock.
  Se usa `npm ci` sobre esos archivos sin resolver durante el build y
  `uv pip install --require-hashes --only-binary :all:` para las herramientas
  Python. Hermes usa `uv sync --frozen` desde su fuente verificada, junto con
  un lock adicional con hashes para setuptools, wheel y packaging. Se usa
  `--no-build-isolation` para impedir instalaciones implícitas de herramientas
  de construcción y `--inexact` para conservar ese backend fijado al sincronizar.
- Los scripts de terceros se ejecutan como `paseo` en una etapa de construcción
  desechable. La etapa final copia únicamente `/opt/paseo-acp`, cambia los
  propietarios a root y elimina escritura de grupo/otros y bits setuid/setgid.
  Las comprobaciones de versiones finales también se ejecutan como `paseo`.
- Se añadieron límites al tamaño de descarga y expansión de archivos y se
  validan nombres de wrappers y variables de entorno antes de generar shell.
- Muse rechaza ejecuciones como root antes de leer o ejecutar su estado en el
  home escribible. Su prueba de staging se ejecuta ahora sin privilegios.
- El daemon exige `PASEO_PASSWORD`: la base únicamente advertía y podía aceptar
  conexiones de control sin autenticación. Configurar el secreto en Dokploy
  antes de recrear el servicio. Las órdenes de consola explícitas se ejecutan
  como paseo después de la reparación y no arrancan automáticamente el daemon.

## Evidencia y limitaciones

Las pruebas Linux cubren el rechazo previo a red sin hash, checksum incorrecto,
lock modificado, dependencia transitiva sin integridad, uso del grafo fijado,
prohibición de instalar como root, expansión de archivos y conservación de
configuración. Las regresiones del init comprueban sustitución de archivo y
ancestro después de `stat`, hardlinks, montajes del mismo dispositivo, rutas
externas, home con ancestro simbólico y falta de información de montajes.
También se mantienen las pruebas de permisos reales como UID 1000 y de Muse.

Resultado local: 28 pruebas del instalador y 9 del init pasan con Python 3.11
de la base real de Paseo. Se construyó `runtime-base` AMD64, incluida la instalación
de uv con hashes obligatorios. Una instalación real de Agoragentic terminó como
UID 1000 usando su lock fijado (98 paquetes). La integración con Tini, gosu y el
entrypoint upstream devolvió `service_uid=1000` y `external_directory_owner=0`
con CODEX_HOME apuntando por enlace a `/etc`.

La instalación real de Hermes también terminó como UID 1000 desde la fuente
verificada, con Python 3.14.9 y el backend setuptools/wheel/packaging protegido
por hashes. La sincronización congelada, sin aislamiento de construcción,
instaló sus dependencias y devolvió `Hermes ACP check OK`.

También se construyó una variante AMD64 con las cinco CLIs npm nativas y Agor,
y pasaron sus comprobaciones de versión. La imagen local de validación final
incorpora el helper y los locks actuales sobre esa variante. Desde su entrypoint
real se comprobaron UID 1000 y 24 780 entradas de artefactos propiedad de root,
sin escritura de grupo/otros ni bits setuid/setgid. Se verificó que el daemon
rechaza un arranque sin contraseña y que Muse rechaza ejecutarse como root.

No se ha construido el catálogo completo ni ARM64, ni se ha iniciado una sesión
autenticada de todos los proveedores. Esas validaciones siguen pendientes antes
del despliegue completo. No se ha modificado el servidor ni se han publicado
imágenes como parte de estas correcciones.

Los ejecutables de Hermes son ahora inmutables para `paseo`: los extras que un
proveedor necesite deben prepararse en el build. Un agente con acceso a archivos
sin sandbox sigue compartiendo las credenciales del mismo UID. Aislar proveedores
requiere contenedores/usuarios y credenciales separados; el sandbox y la política
del despliegue real todavía deben verificarse.

Las configuraciones existentes con comandos `npx`/`uvx` se conservan. Para usar
las versiones fijadas de la imagen, cambiar sus comandos a los wrappers absolutos
indicados en [agentes ACP](acp-providers.md); conservar opciones y variables.

Se corrigió además el fallo de instalación de Cline 3.0.73: `npm ci` puede dejar
el binario instalado sin crear `node_modules/.bin/cline`. El instalador usa ahora
la ruta `bin` declarada en el lock revisado, comprueba su confinamiento y permisos
después de los scripts npm, y sigue fallando si falta el archivo real. Las pruebas
cubren el enlace ausente, una ruta no revisada, escapes de directorio y redirección
del paquete durante postinstall. Todas las recetas npm se contrastan con sus
entradas `bin` en los locks. Las capas nativas y ACP se separaron y las descargas
npm/uv se almacenan en cachés BuildKit por arquitectura; esas cachés no se copian
a la imagen final.

La corrección de Cline se verificó con instalaciones reales como UID 1000 en
AMD64 y ARM64 (esta última bajo emulación), y ambos lanzadores devolvieron
`3.0.73`. En AMD64 se confirmó además que `.bin/cline` seguía ausente, por lo
que la prueba ejercita el caso original. Las cinco CLIs npm nativas existentes
conservan ejecutables compatibles con las rutas revisadas. El Dockerfile pasa
`docker buildx build --check`; esto no equivale a completar el catálogo completo.

Muse mantiene su mecanismo oficial de actualizaciones en el home: valida el
binario contra el SHA-256 de su manifiesto publicado, pero la versión estable
puede cambiar durante la ejecución. El wrapper rechaza root y su launcher se
verifica con el hash fijado. Este mecanismo requiere confiar en el servicio de
distribución de Muse y no equivale a una versión binaria congelada en la imagen.
