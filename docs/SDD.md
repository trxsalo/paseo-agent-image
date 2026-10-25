# SDD: Entorno persistente de Paseo en Docker

Estado: Diseño de referencia; validar su aplicación en cada despliegue.

## Objetivo

Ejecutar Paseo y sus agentes dentro de Docker con:
- Proyectos y configuración persistentes.
- Terminal funcional para los agentes.
- Proveedores instalados y autenticados.
- Permisos limitados y documentados.
- Instalación, actualización y recuperación reproducibles.

## Requisitos del entorno

- Verificar el acceso a la interfaz y la conexión del cliente al daemon.
- Verificar volúmenes, usuario, puertos, proveedores y permisos de Docker
  en cada despliegue.
- Comprobar que el kernel y las restricciones del runtime permiten el sandbox
  del agente. El error `bwrap: No permissions to create a new namespace`
  indica una incompatibilidad que debe diagnosticarse según la sección
  «Sandbox y terminal».
- Validar la terminal desde una sesión del agente con la política de sandbox
  prevista para el despliegue.

## Arquitectura

Servidor Docker
└── Contenedor Paseo
    ├── Daemon de Paseo
    ├── Agentes y proveedores
    ├── Herramientas de desarrollo
    ├── Directorio persistente de proyectos
    └── Estado y configuración persistentes

El acceso al servidor anfitrión no forma parte del diseño inicial.

## Almacenamiento

Separar:
1. Proyectos: bind mount para acceder al código desde el servidor.
2. Estado de Paseo: volumen persistente en su ruta real.
3. Configuración y autenticación de proveedores:
   persistir las rutas necesarias según cada proveedor.

Confirmar las rutas reales antes de redactar el Compose definitivo.
Los volúmenes con credenciales deben tener acceso restringido.

## Usuario y permisos

- Ejecutar el servicio con un usuario sin privilegios.
- Documentar su UID/GID.
- Alinear permisos con los directorios montados.
- Evitar permisos globales de escritura.
- No montar el socket de Docker por defecto.

## Sandbox y terminal

Diagnosticar la interacción entre:
- Sandbox del agente y bubblewrap.
- Namespaces del kernel del servidor.
- Perfil seccomp y otras restricciones del runtime.
- Usuario y configuración de Docker.

Seleccionar el cambio mínimo que permita ejecutar el sandbox.
No asumir que privileged: true es necesario.

Si el entorno no admite el sandbox, documentar la alternativa
soportada por el agente y su implicación de seguridad.
La ejecución sin sandbox no debe activarse silenciosamente.

## Imagen

- Partir del Dockerfile existente.
- Fijar versiones para las publicaciones.
- Incluir las dependencias de ejecución verificadas.
- Separar herramientas opcionales en imágenes derivadas.
- Conservar el comportamiento de inicio y parada del servicio.

## Operación

Documentar:
- Instalación inicial.
- Registro de proyectos y creación de workspaces.
- Autenticación de proveedores.
- Actualización y reversión.
- Copia de seguridad y restauración.
- Diagnóstico de terminal y permisos.

## Entregables previstos

Esta lista describe el despliegue de referencia; no todos los archivos se
incluyen en el repositorio.

- Dockerfile revisado.
- docker-compose.yml.
- .env.example sin secretos.
- Guía de operación.
- Registro de validación y limitaciones.
