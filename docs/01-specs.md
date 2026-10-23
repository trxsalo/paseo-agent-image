# Especificaciones y aceptación

## SPEC-01: Persistencia de proyectos

Requisito:
El código reside en un directorio persistente del servidor.

Aceptación:
Crear un archivo desde un agente, recrear el contenedor y
comprobar que conserva contenido y permisos.

## SPEC-02: Persistencia del estado

Requisito:
Conservar configuración, registro de proyectos y los datos
de sesión que Paseo almacene en disco.

Aceptación:
Registrar un proyecto, recrear el contenedor y comprobar
que sigue disponible.

## SPEC-03: Autenticación de proveedores

Requisito:
Cada proveedor documenta instalación, autenticación y
rutas persistentes necesarias.

Aceptación:
El proveedor inicia una sesión antes y después de recrear
el contenedor sin perder su autenticación persistible.

## SPEC-04: Terminal y sandbox

Requisito:
El agente puede ejecutar comandos con la política de
sandbox seleccionada y documentada.

Aceptación:
- Ejecutar pwd y git --version.
- Crear y leer un archivo dentro del proyecto.
- Ejecutar una comprobación propia del proyecto.
- Verificar que el sandbox limita el acceso según su política.
- Confirmar que no aparece el error de namespaces de bwrap.

## SPEC-05: Permisos

Requisito:
Paseo funciona como usuario sin privilegios y puede escribir
en los montajes autorizados.

Aceptación:
Comprobar identidad del proceso y escritura desde el agente
y desde el servidor, sin recurrir a chmod 777.

## SPEC-06: Varios proyectos

Requisito:
Registrar y utilizar proyectos independientes.

Aceptación:
Crear dos proyectos, abrir un workspace en cada uno y
comprobar que cada sesión trabaja en su directorio.

## SPEC-07: Ciclo de vida

Requisito:
Inicio, parada y actualización reproducibles.

Aceptación:
- docker compose config valida la configuración.
- El servicio inicia y acepta conexiones.
- La parada permite finalizar el servicio correctamente.
- La actualización conserva proyectos y estado.
- Se documenta cómo volver a la versión anterior y
  cualquier limitación por cambios de formato de datos.

## SPEC-08: Copias de seguridad

Requisito:
Respaldar proyectos y estado, incluidas las rutas de
autenticación necesarias, con protección de secretos.

Aceptación:
Restaurar una copia en un entorno separado y comprobar
proyectos, configuración y acceso de los proveedores.

## SPEC-09: Exposición de red

Requisito:
Documentar dirección de escucha, puertos, autenticación
y método de acceso remoto.

Aceptación:
La interfaz es accesible desde el cliente previsto y
los puertos publicados coinciden con la configuración.