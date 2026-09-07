"""Nombres legacy BioAgro → XeniaMAP (F1). No renombrar en caliente sin plan dual."""

# Volumen Docker de Postgres
#
# Nombre real en docker-compose: ``bioagromap_postgres_data``
# Motivo: datos vivos en máquinas de desarrollo/producción. Renombrar implica
# ``docker volume create`` + copia o re-attach; no hacerlo en un deploy casual.
#
# Disco externo
#
# Actual: ``Data_XeniaMap`` / ``EXTERNAL_DATA_HOST_PATH`` → ``/data_xeniamap``
# Antiguo: ``Data_Bioagro`` / ``/data_bioagro`` — si aún existe en el host,
# crear symlink o actualizar EXTERNAL_DATA_HOST_PATH.
#
# SessionStorage / eventos
#
# Vigentes: ``xeniamap_access``, ``xeniamap_refresh``, ``xeniamap:auth-*``
# Legacy ``bioagromap_*`` eliminados del código (F1); ``clearAuthTokens`` limpia residuos.
#
# Assets
#
# Eliminado: ``frontend/public/logo-bioagro.png``
# Carpeta ``logo/LOGO-BIOAGRO-*.png`` y ``backups/bioagromap_*``: archivo histórico, fuera del runtime.
