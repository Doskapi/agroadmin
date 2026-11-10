# Gestión Agro

API para administrar la empresa: facturas de proveedores (con extracción automática desde PDF o foto),
cartas de porte, campos/lotes/campañas, reportes y dashboards. Usuarios con roles y permisos.

**Stack:** Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2 + Alembic · Claude (extracción con IA) · Metabase (dashboards)

## Arrancar

```bash
cp .env.example .env        # completar SECRET_KEY, ADMIN_PASSWORD y (opcional) ANTHROPIC_API_KEY
docker compose up -d --build
```

- **Interfaz web: http://localhost:8080** (entrar con el `ADMIN_EMAIL` / `ADMIN_PASSWORD` del `.env`)
- Documentación interactiva de la API: http://localhost:8080/api/docs (solo con `DOCS_PUBLICAS=true`)
- Dashboards a medida (opcional): `docker compose --profile dashboards up -d` → http://localhost:3000
  (solo desde esta máquina; en Metabase, conectar a Postgres con host `db`, base `agro`, usuario `agro`)

Al arrancar, el contenedor aplica las migraciones y crea permisos, roles, categorías y el usuario admin del `.env`.

## Seguridad

- **Claves obligatorias.** Con `ENTORNO=produccion` (el valor por defecto) la API no arranca si `SECRET_KEY`
  falta, es de ejemplo o tiene menos de 32 caracteres, y no crea el admin si `ADMIN_PASSWORD` es débil.
  Las contraseñas de usuarios deben tener 10 caracteres o más.
- **Solo nginx está publicado.** La base y la API no tienen puertos abiertos: se llega a la API por `/api/*`.
- **HTTPS.** En un servidor con dominio propio: poner `DOMINIO=agro.miempresa.com.ar` en el `.env`, abrir los
  puertos 80 y 443 y correr `docker compose --profile https up -d`. Caddy saca y renueva el certificado solo.
  En ese caso conviene no exponer `WEB_PUERTO` a internet (firewall).
- **Cabeceras de seguridad** (CSP, `X-Frame-Options`, `nosniff`, HSTS con HTTPS) en todas las respuestas.
- **Login.** Tras 5 intentos fallidos para un mismo email (o 20 desde una misma IP) en 15 minutos, el login
  responde 429 hasta que pase la ventana. nginx además limita a 10 intentos por minuto por IP.
- **Archivos.** El tipo se detecta por el contenido (no por lo que declara el navegador); se rechazan PDFs
  dañados, con contraseña o de más de 30 páginas, y archivos de más de 20 MB.
- **Siempre queda un administrador.** No se puede desactivar ni quitarle el permiso al último usuario activo
  con `usuarios:admin`.

## Backups

El servicio `backup` hace una copia al arrancar y después una por día (a las `BACKUP_HORA`, hora de Argentina)
en `./backups`: la base (`agro_FECHA.dump`) y los archivos de facturas (`archivos_FECHA.tar.gz`). Borra las de
más de `BACKUP_DIAS` días. **Copiá esa carpeta a otro lugar** (otro disco, la nube): si se rompe el servidor,
un backup en el mismo disco no sirve.

```bash
# copia ahora mismo
docker compose run --rm backup ahora

# restaurar la base
docker compose exec -T db pg_restore -U agro -d agro --clean --if-exists < backups/agro_FECHA.dump

# restaurar los archivos
docker compose run --rm --entrypoint sh -v agroadmin_archivos:/data/archivos backup \
  -c "tar xzf /backups/archivos_FECHA.tar.gz -C /data"
```

## Cómo se carga una factura

1. `POST /facturas/importar` con el PDF o la foto → responde enseguida con estado `procesando`.
2. En segundo plano:
   - **QR de ARCA**: se busca en los links del PDF, en el texto y en la imagen. De ahí salen CUIT, tipo,
     punto de venta, número, fecha, total, moneda y CAE (son datos oficiales y tienen prioridad).
   - **Claude** (si hay `ANTHROPIC_API_KEY`): lee el comprobante completo y aporta razón social, neto, IVA,
     percepciones, ítems y una categoría sugerida. Si algo no coincide con el QR, queda una advertencia.
   - Se crea el proveedor si no existía y se detectan comprobantes duplicados.
3. La factura queda `pendiente_revision`. Alguien la revisa (`PATCH /facturas/{id}`), le asigna
   campaña/campo/lote/categoría y la confirma (`POST /facturas/{id}/confirmar`).
4. Solo las facturas **confirmadas** cuentan en los reportes. Las notas de crédito restan, y los montos en dólares
   se pasan a pesos con la cotización del comprobante.

## Roles iniciales

| Rol | Puede |
|---|---|
| `admin` | Todo, incluido crear usuarios y editar roles |
| `administrativo` | Cargar/editar facturas y cartas de porte, catálogos, reportes |
| `contador` | Ver todo, confirmar/anular facturas, reportes |
| `campo` | Cargar cartas de porte |

Los roles se editan con `PUT /roles/{nombre}` (lista de permisos en `GET /permisos`).

## Endpoints principales

| | |
|---|---|
| `POST /auth/login` | Token (usuario = email) |
| `/usuarios`, `/roles`, `/permisos` | Administración de accesos |
| `/proveedores`, `/campos`, `/campos/{id}/lotes`, `/campanias`, `/categorias` | Catálogos |
| `/facturas` (+ `/importar`, `/{id}/confirmar`, `/{id}/anular`, `/{id}/reprocesar`, `/{id}/archivo`) | Facturas |
| `/cartas-porte` | Cartas de porte |
| `GET /reportes/gastos?agrupar=mes\|categoria\|proveedor\|campo\|campania` | Reporte de gastos (JSON) |
| `GET /reportes/gastos.xlsx?...` | El mismo reporte en Excel |
| `GET /reportes/resumen` | Datos del dashboard |

## Desarrollo

```bash
# en tu máquina podés poner ENTORNO=desarrollo en el .env para usar claves de prueba

# tests (usan una base agro_test aparte, con las migraciones reales)
docker compose run --rm -v "$PWD:/app" api python -m pytest -q

# nueva migración después de cambiar app/models.py
docker compose run --rm -v "$PWD:/app" api alembic revision --autogenerate -m "descripcion"

# frontend con recarga en caliente (no hace falta tener Node instalado): http://localhost:5173
docker compose --profile dev up web-dev
```

El frontend (`frontend/`) es React + TypeScript + Vite, con TanStack Query para los datos y Recharts para
los gráficos. En producción lo sirve nginx (`web`), que también redirige `/api/*` al backend. Las pantallas
y botones se muestran según los permisos del usuario.

## Estructura

```
app/
  main.py            app FastAPI
  models.py          tablas
  schemas.py         entrada/salida de la API
  security.py        contraseñas, JWT, catálogo de permisos y roles iniciales
  deps.py            usuario actual y `requiere("permiso")`
  seed.py            datos iniciales
  limite_login.py    bloqueo de intentos de login fallidos
  validar_archivo.py tipo real, tamaño y páginas de los archivos subidos
  routers/           endpoints por módulo
  extraccion/        QR de ARCA, PDF, Claude y el pipeline que los combina
alembic/             migraciones
scripts/backup.sh    copias diarias (servicio `backup`)
Caddyfile            HTTPS (perfil `https`)
tests/
frontend/
  src/pages/         Dashboard, Facturas, FacturaDetalle (revisión), CartasPorte, Reportes, Catalogos, Usuarios
  src/components/    Layout (menú), gráficos, controles comunes
  src/api.ts         cliente HTTP con el token
  src/auth.tsx       sesión y permisos
```

## Próximos pasos sugeridos

- Validar CAE contra el web service de ARCA (`WSCDC`) y emitir cartas de porte electrónicas (`WSCPE`).
- Cola de tareas (Celery/RQ + Redis) cuando el volumen de importaciones crezca.
- Ventas de granos, liquidaciones, stock de insumos, labores por lote → costo por hectárea.
