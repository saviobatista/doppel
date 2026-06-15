#!/bin/sh
set -e

# Só o processo da API aplica as migrations no boot (idempotente). O worker
# espera o schema pelo seu proprio loop de retry. Em prod, o Helm Job ja
# aplicou antes; aqui vira no-op.
case "$1" in
  uvicorn)
    echo "entrypoint: alembic upgrade head"
    alembic upgrade head
    ;;
esac

exec "$@"
