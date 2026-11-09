# Actualizar la imagen a Paseo 0.15.3

## Petición

«sigue siendo el tag, lastest, prepra los cambios para actualizar y lanzar el worker para que se compile en github en mi repositorio»

«si hay que actualizar el workflow hazlo»

«el server host es amd64, estonces los build en el worfklow que sean solo para este , ya que demora mucho el de arm»

## Alcance y decisiones

- Base estable oficial Paseo 0.15.3, fijada por digest multi-arquitectura.
- Publicación en Docker Hub con etiqueta `latest`, solo AMD64; quitar QEMU del workflow.
- Una unidad: Dockerfile, configuración de CI y documentación de actualización.
- Publicar desde `update/paseo-0.15.3` y ejecutar `publish.yml` en esa rama.
- No desplegar ni reiniciar el contenedor en ejecución (actualmente 0.12.0).
- Configurar las variables Actions requeridas; reutilizar el secreto existente.

## Estado

Cambios publicados en la rama `update/paseo-0.15.3`.
Primera compilación multi-arquitectura: commit `4613cd4`.

Workflow lanzado: https://github.com/trxsalo/paseo-agent-image/actions/runs/42559010500

La ejecución anterior seguía en curso al preparar el cambio a AMD64.
Se cancelará y se lanzará una nueva ejecución desde el commit con AMD64. Pasaron las validaciones de
configuración, sintaxis, permisos persistentes, Muse, instalador ACP y límites
de seguridad del init. Queda pendiente el resultado del build AMD64
y de la publicación. Las variables Actions ya están configuradas para publicar
`docker.io/trxsalo/paseo-agent-clis:latest`.

## Verificación

- El registro oficial devuelve el mismo digest para `latest` y `0.15.3`:
  `sha256:57048c43a2c2988434273c7f8a4b25aa585bca6c1720493ae52e2fa91497b99a`.
- Índice con distribuciones Linux AMD64 y ARM64.
- EntryPoint oficial revisado: conserva rutas y delegación de comandos.
- Pasan 30 pruebas del instalador y la prueba de Muse.
- Pasan sintaxis de shell/JavaScript y `git diff --check`.
- Build local no disponible: este entorno no tiene Docker.

## Aceptación y próximo paso

Consultar la ejecución más reciente de `publish.yml` en `update/paseo-0.15.3`
para comprobar el resultado (la anterior se cancela por el cambio a AMD64). Si falla, leer
los logs y corregir la causa antes de relanzar. Si pasa, registrar el digest
publicado. No afirmar una compilación correcta antes de que termine CI.
El merge de la rama y el despliegue del contenedor quedan pendientes.

## Riesgos y recuperación

Recrear el contenedor detiene los procesos actuales. Respaldar `/home/paseo`
y `/workspace` antes del despliegue. Para rollback usar la imagen anterior y el
respaldo compatible de configuración si la nueva versión modifica su formato.
El hallazgo previo sobre contraseña en comandos explícitos queda fuera de esta
actualización de base y no se considera corregido.
