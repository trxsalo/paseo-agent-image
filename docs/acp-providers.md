# Agentes ACP en la imagen de Paseo

El build instala los agentes compatibles con Linux del inventario revisado en
`docker/acp-catalog.lock.json`. El catálogo se obtiene del código oficial de
[Paseo](https://github.com/getpaseo/paseo/blob/d972f67c3fea06fbc163608f5ddcc2c443de83ac/packages/app/src/data/acp-provider-catalog.ts)
y las distribuciones del [registro ACP](https://agentclientprotocol.com/registry).
Se fijan las versiones disponibles de las distribuciones; pueden diferir de las
versiones del catálogo de la interfaz de Paseo. El Dockerfile no descarga un
catálogo cambiante durante el build.

Cada paquete npm se instala en su propio directorio, con verificación de la
integridad del paquete principal antes de ejecutar scripts de instalación. Los
agentes Python tienen entornos separados. Se conservan los recursos auxiliares
de los binarios y se exige un SHA-256 previamente revisado; sin él no se descargan
ni instalan. Los grafos npm completos se conservan en `docker/dependency-locks`,
incluidas sus integridades. Python usa requisitos con hashes obligatorios y
Hermes conserva su lockfile de ejecución upstream y usa un lock adicional con
hashes para setuptools, wheel y packaging, sin instalar dependencias implícitas
de construcción. El build no vuelve a resolver dependencias.
La instalación de código de terceros ocurre en una etapa sin privilegios; los
artefactos finales son propiedad de root y no son escribibles por los agentes.

## Cobertura del inventario

Esta tabla describe las recetas preparadas, no una autenticación o sesión real
validada con todos los proveedores. `paseo-acp list` muestra el resultado efectivo
de la instalación en la imagen construida.

| ID para configurar | Agente | AMD64 | ARM64 |
| --- | --- | --- | --- |
| agoragentic-acp | Agoragentic | Sí | Sí |
| amp-acp | Amp y su CLI subyacente | Sí | Sí |
| auggie | Auggie | Sí | Sí |
| autohand | Autohand nativo 0.9.8, sustituye al adaptador retirado | Sí | Sí |
| cline | Cline | Sí | Sí |
| codebuddy-code | Codebuddy | Sí | Sí |
| codewhale | CodeWhale | Sí | Sí |
| cortex-code | Cortex Code | Bloqueado: sin hash | Bloqueado: sin hash |
| corust-agent | Corust | Sí | No publicado |
| crow-cli | crow-cli | Sí | Sí |
| cursor | Cursor | Bloqueado: sin hash | Bloqueado: sin hash |
| deepagents | DeepAgents | Sí | Sí |
| devin | Devin | Bloqueado: sin hash | Bloqueado: sin hash |
| dimcode | DimCode | Sí | Sí |
| dirac | Dirac | Sí | Sí |
| factory-droid | Factory Droid | Sí | Sí |
| fast-agent | fast-agent | Sí | Sí |
| gemini | Gemini CLI | Sí | Sí |
| gjc | Gajae Code | Sí | Sí |
| glm-acp-agent | GLM Agent | Sí | Sí |
| goose | goose | Sí | Sí |
| grok | Grok Build | Sí | Sí |
| hermes | Hermes v0.22.4 con ACP | Sí | Sí |
| hoplite | Hoplite | Sí | Sí |
| junie | Junie | Sí | Sí |
| kilo | Kilo | Sí | Sí |
| kiro | Kiro CLI | Sí | Sí |
| kimi | Kimi CLI | Sí | Sí |
| minimax-code | MiniMax Code | Sí | Sí |
| minion-code | Minion Code | Sí | Sí |
| mistral-vibe | Mistral Vibe | Sí | Sí |
| nova | Nova | Sí | Sí |
| poolside | Poolside | Sí | Sí |
| qoder | Qoder | Sí | Sí |
| qwen-code | Qwen Code | Sí | Sí |
| sigit | siGit | Sí | Sí |
| stakpak | Stakpak | Sí | Sí |
| traecli | TRAE CLI | Pendiente | Pendiente |
| vtcode | VT Code | Sí | No publicado |
| copilot-acp | Copilot ya instalado, reutilizado por ACP | Sí | Sí |

TRAE queda pendiente: el instalador oficial devolvió HTTP 403 en el entorno de
preparación y no se pudo obtener una distribución verificable. No se incluye un
comando que pretenda tenerlo instalado. Corust y VT Code se omiten en ARM64 porque
el registro consultado solo publica Linux x86_64. Los demás errores de descarga o
instalación detienen el build y muestran el ID del agente que falló.

Tras el endurecimiento, Cortex Code, Cursor y Devin quedan bloqueados en ambas
arquitecturas porque sus seis distribuciones no tienen un SHA-256 revisado. Se
recuperaron digests publicados por GitHub para las otras ocho distribuciones que
carecían de ellos. El inventario conserva las recetas bloqueadas y el motivo se
incluye en `paseo-acp list`; añadir un hash requiere obtener y revisar el artefacto
de la fuente oficial. La cobertura de recetas habilitadas es 36/40 en AMD64 y
34/40 en ARM64, sujeta a la validación del build de cada arquitectura.

## Construir

El build normal incluye todas las recetas compatibles, además de los agentes
nativos existentes. Requiere descargar numerosos paquetes y binarios; el tamaño
y el tiempo de construcción aumentan considerablemente.

```bash
docker build -t paseo-agent-clis:acp .
# Variante opcional para instalar solo algunos ACP:
docker build --build-arg ACP_AGENTS=hermes,gemini,kimi -t paseo-agent-clis:acp-selected .
```

Conservar `/home/paseo` y `/workspace` al recrear el contenedor. La instalación de
los ejecutables reside en `/opt/paseo-acp` dentro de la imagen y no queda oculta
por un volumen antiguo de `/home/paseo`. El init mantiene la reparación de
propietarios del home y la reparación de permisos de GitHub CLI.

## Activar en Paseo

Desde el host Docker, reemplazar `paseo` por el nombre real del contenedor:

```bash
docker exec --user paseo paseo paseo-acp list
docker exec --user paseo paseo paseo-acp configure hermes gemini
docker exec --user paseo paseo paseo reload
```

Para registrar todos los instalados, sustituir la segunda línea por:

```bash
docker exec --user paseo paseo paseo-acp configure --all
```

Activar todos aumenta el trabajo de descubrimiento y puede mostrar solicitudes
de autenticación de varios proveedores. Conviene comenzar con los que se usarán.
El helper añade proveedores ACP a `$PASEO_HOME/config.json` (normalmente
`/home/paseo/.paseo/config.json`), conserva entradas ya existentes y guarda una
copia privada antes de escribir. No reemplaza configuraciones personalizadas.
Utiliza comandos absolutos `paseo-acp-<id>` que ejecutan la versión instalada;
no requiere `npx` ni `uvx` para descargar el agente durante su lanzamiento.

El catálogo de la interfaz puede escribir comandos distintos al añadir un agente.
Si ya existe una entrada con `npx`/`uvx`, el helper la conserva: cambiar manualmente
solo su `command` a `["/opt/paseo-acp/bin/paseo-acp-<id>"]` si se quiere utilizar la
versión de esta imagen. Mantener las opciones y variables personalizadas.

## Autenticar

Ejecutar cada CLI normal como `paseo`, nunca como root. Por ejemplo:

```bash
docker exec -it --user paseo paseo hermes model
docker exec --user paseo paseo hermes acp --check
docker exec -it --user paseo paseo gemini
docker exec -it --user paseo paseo kimi
docker exec -it --user paseo paseo amp login
```

Consultar el enlace `documentation` de cada entrada del inventario para el flujo
de ese proveedor. Suscripciones, claves y acceso a modelos son independientes de
la instalación del binario. No se incorporan credenciales a la imagen. Mantener
el estado bajo `/home/paseo`; si se cambia una ruta de configuración a otro
directorio, persistirla por separado. No montar credenciales del servidor anfitrión.

Hermes usa Python 3.14.9 y el extra `acp`, instalados desde un commit fijado de
`v0.22.4` y su lockfile. Su checkout y venv ahora son propiedad de root. Si el
proveedor elegido necesita un extra Python que no viene incluido, debe añadirse
deliberadamente al build y reconstruir la imagen; la preparación automática de
dependencias dentro de `/opt` en ejecución queda restringida. Configuración,
memoria y credenciales en `~/.hermes` siguen siendo escribibles por el usuario y
persisten con el volumen. Navegadores y otros componentes opcionales no se
preinstalan. Esta propiedad de los ejecutables no aísla las credenciales entre
agentes del mismo usuario: para ello se requieren contenedores/usuarios separados.

## Validar y actualizar

`paseo-acp check` comprueba presencia y sintaxis de los lanzadores sin autenticar.
Las pruebas de `tests/test_acp_installer.py` cubren extracción segura, checksum,
argumentos, arquitecturas ausentes y conservación de configuración. No sustituyen
una sesión ACP real con credenciales ni la prueba de persistencia tras recrear.

Para actualizar deliberadamente el inventario:

```bash
node scripts/snapshot-acp-catalog.mjs
node scripts/lock-dependencies.mjs
# Con uv 0.13.5 disponible, preferiblemente en un entorno Linux:
python scripts/lock-python.py
```

Revisar el diff de versiones, URLs, hashes y requisitos antes de construir. El
script conserva adaptaciones explícitas para Hermes, Autohand, CodeWhale, Amp,
Kiro, Gajae Code y Hoplite; revisar también esas adaptaciones al actualizarlos.
`lock-dependencies.mjs` resuelve solo metadatos, con scripts desactivados, y exige
integridades de los paquetes. `lock-python.py` resuelve solo wheels y genera
hashes. Los locks nativos están referenciados en `docker/native-clis.lock.json`.
