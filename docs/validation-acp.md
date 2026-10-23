# Validación ACP — 2026-10-22

Registro de la implementación inicial. Las correcciones y verificaciones
posteriores de seguridad están en `security-fixes.md`.

## Comprobado

- Sintaxis de los scripts de shell y de `scripts/snapshot-acp-catalog.mjs`.
- Diez pruebas de `tests/test_acp_installer.py` en un contenedor Linux Python 3.12,
  sin red ni credenciales: extracción segura, integridad, argumentos, variables
  personalizadas, ausencia de arquitectura y conservación de configuración.
- Prueba de reparación de propietarios/permisos, incluida lectura/escritura de
  configuración de gh como UID/GID 1000:1000 y protección de enlaces externos.
- Prueba del lanzador de Muse.
- Instalación real de Hermes desde el commit fijado, con `uv==0.13.5`, Python
  3.14.9 y las 69 dependencias del lockfile más el extra ACP. Resultado de
  `hermes acp --check`: `Hermes ACP check OK`. Esta comprobación se ejecutó
  como root en un contenedor temporal, sin autenticar un proveedor.
- SHA-256 del archivo fuente de Hermes incorporado al inventario después de
  descargarlo y calcularlo localmente.
- `git diff --check` sin errores de espacios.

## Pendiente en CI y despliegue

- El build completo local se intentó, pero no se completó. Se interrumpió
  mientras continuaba el `npm install --global` de las CLIs preexistentes;
  todavía no había alcanzado la instalación del nuevo catálogo ACP. No se
  obtuvo una imagen final ni se verificaron todas las recetas contra la base
  de Paseo, y no se publicó ni desplegó ninguna imagen.
- Construcción y comprobaciones de la imagen completa en AMD64 y ARM64.
  El workflow ejecuta las pruebas y `paseo-acp check` durante el build.
- Autenticación y una sesión ACP real por cada proveedor que se vaya a usar.
- Autenticación persistente después de recrear el contenedor.
- Diagnóstico del error de namespaces de bubblewrap en el servidor real.
- TRAE: instalador oficial inaccesible con HTTP 403 durante la preparación.
  Corust y VT Code: sin distribución Linux ARM64 en el registro consultado.

El inventario de recetas no debe interpretarse como certificación de todos los
proveedores ni como evidencia de que ya estén disponibles en el servidor.
