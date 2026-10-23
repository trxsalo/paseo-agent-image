# Guía de implementación

1. Inventariar el despliegue actual
   Recoger Dockerfile, Compose, versiones, usuario,
   montajes, puertos y proveedores.

2. Respaldar los datos existentes
   Localizar el código y el estado antes de cambiar montajes.
   Un montaje nuevo puede ocultar archivos existentes
   en la ruta del contenedor.

3. Diagnosticar bwrap
   Recoger versiones del kernel, Docker y agente,
   configuración de seguridad y error completo.
   Reproducir con un comando mínimo.

4. Resolver la ejecución del sandbox
   Aplicar el ajuste mínimo respaldado por el diagnóstico.
   Verificar su funcionamiento y sus límites.

5. Implementar persistencia
   Configurar proyectos, estado y autenticación.
   Corregir permisos según UID/GID.

   Para GitHub CLI, el init ejecuta inicialmente el helper seguro como root,
   baja a paseo con gosu y delega al entrypoint original sin privilegios.
   Antes de esa delegación, reparar
   propietario 1000:1000 y permisos privados de la configuración de gh:
   directorios 700 y archivos 600 mediante descriptores verificados. La ruta es
   GH_CONFIG_DIR o, en su defecto, XDG_CONFIG_HOME/gh (~/.config/gh).
   Asegurar acceso del propietario a /home/paseo y al directorio XDG.
   Autenticar siempre como paseo; la reparación se aplica al arrancar.

   Validación de SPEC-03 y SPEC-05: ejecutar gh auth status como paseo antes
   y después de recrear el contenedor conservando /home/paseo. La prueba
   tests/test_permissions_entrypoint.py reproduce archivos de gh sin acceso
   y comprueba lectura/escritura con UID/GID 1000:1000. Esa prueba no sustituye
   la validación de autenticación y persistencia en el despliegue real.

6. Preparar la imagen
   Añadir únicamente proveedores y herramientas acordados.
   Fijar versiones y documentar el arranque.

   El inventario ACP y las recetas Linux se mantienen en
   docker/acp-catalog.lock.json. El Dockerfile instala los agentes compatibles
   con la arquitectura elegida; las exclusiones quedan registradas en
   /opt/paseo-acp/installed.json. Consultar docs/acp-providers.md para activar
   agentes como paseo y autenticar cada proveedor. La instalación de paquetes
   no acredita una sesión ACP real ni resuelve la restricción de namespaces.

7. Completar Compose y .env.example
   Utilizar rutas, puertos y comandos verificados.
   Excluir secretos del repositorio.

8. Validar las especificaciones
   Guardar resultados y limitaciones observadas.

9. Preparar la contribución
   Incluir cambios, guía, ejemplo de configuración
   y evidencia de validación.
