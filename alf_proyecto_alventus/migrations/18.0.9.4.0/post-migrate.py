# -*- coding: utf-8 -*-
"""
Migracion 18.0.9.4.0
---------------------
Repite el backfill de "date_start"/"date" para los viajes (project.project)
que ya existian, esta vez con dos mejoras sobre el intento de la migracion
18.0.9.3.0 (que para algunos viajes no encontro ninguna fecha):

1. El texto de las etapas no siempre tiene el formato "dd/mm/yyyy" (con
   barras y año de 4 cifras) que se usa desde los asistentes actuales.
   Etapas mas antiguas se guardaron como "dd-mm-yy" (con guiones y año de
   2 cifras), p.ej. "Dia 1 - 19-08-26". Ahora el patron admite ambos
   separadores ("/" o "-") y años de 2 o 4 cifras.

2. Ademas del texto de la etapa, tambien se mira la fecha limite
   ("date_deadline") de las tareas del viaje, por si el texto de la etapa
   no lleva fecha pero las tareas si la tienen (es el caso de viajes
   creados con el asistente antiguo, donde las etapas se llaman solo
   "Dia 1", "Dia 2", etc., sin fecha en el nombre, pero cada tarea si
   tiene su date_deadline puesta).

Igual que antes: no se toca ningun proyecto que ya tenga "date_start" o
"date" puestos a mano, y la fecha de inicio excluye la etapa "Dia 0"
(preparativos antes de salir, sequence == 0).
"""
import logging
import re

_logger = logging.getLogger(__name__)

# Admite "dd/mm/yyyy" y "dd-mm-yy" (y combinaciones), con año de 2 o 4 cifras.
STAGE_DATE_RE = re.compile(r'(\d{2})[/-](\d{2})[/-](\d{2}|\d{4})')


def migrate(cr, version):
    if not version:
        return

    env = _get_env(cr)
    Project = env['project.project']
    Stage = env['project.task.type']
    Task = env['project.task']

    projects = Project.with_context(active_test=False).search([
        '|', ('date_start', '=', False), ('date', '=', False),
    ])
    _logger.info("[alf_proyecto_alventus] Backfill de fechas 18.0.9.4.0: %d proyectos a revisar", len(projects))

    updated = 0
    for project in projects:
        stages = Stage.search([('project_ids', 'in', project.id)])
        tasks = Task.with_context(active_test=False).search([('project_id', '=', project.id)])

        # (sequence, 'YYYY-MM-DD') candidatas, de dos origenes distintos.
        dated = []

        for stage in stages:
            match = STAGE_DATE_RE.search(stage.name or '')
            if not match:
                continue
            day, month, year = match.groups()
            if len(year) == 2:
                year = '20' + year
            dated.append((stage.sequence, f"{year}-{month}-{day}"))

        for task in tasks:
            if not task.date_deadline:
                continue
            seq = task.stage_id.sequence if task.stage_id else None
            dated.append((seq, task.date_deadline.isoformat()))

        if not dated:
            continue

        end_date = max(d for _seq, d in dated)

        non_day0 = [d for seq, d in dated if seq != 0]
        start_date = min(non_day0) if non_day0 else min(d for _seq, d in dated)

        vals = {}
        if not project.date_start:
            vals['date_start'] = start_date
        if not project.date:
            vals['date'] = end_date

        if vals:
            project.write(vals)
            updated += 1

    _logger.info("[alf_proyecto_alventus] Backfill de fechas 18.0.9.4.0: %d proyectos actualizados", updated)


def _get_env(cr):
    from odoo import api, SUPERUSER_ID
    return api.Environment(cr, SUPERUSER_ID, {})
