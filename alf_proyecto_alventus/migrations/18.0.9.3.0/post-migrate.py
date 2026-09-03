# -*- coding: utf-8 -*-
"""
Migracion 18.0.9.3.0
---------------------
Rellena, para los viajes (project.project) que ya existian antes de este
cambio, los campos estandar de Odoo "date_start" (Fecha de inicio) y "date"
(Fecha de fin), a partir de las etapas ("Dia N - dd/mm/yyyy") que ya tiene
cada proyecto. Los viajes nuevos ya se rellenan solos desde los asistentes
de creacion / importacion ICS, asi que esto es solo para los que ya estaban
creados.

- "Fecha de inicio" = la etapa con la fecha mas antigua, EXCLUYENDO la etapa
  "Dia 0" (preparativos antes de salir, sequence == 0), ya que esa no es un
  dia de viaje real.
- "Fecha de fin" = la etapa con la fecha mas reciente (aqui si se tiene en
  cuenta cualquier etapa, "Dia 0" incluida si la hubiera, pero al ser
  siempre la mas temprana no afecta al maximo).

No se toca ningun proyecto que ya tenga "date_start" o "date" puestos a
mano, para no pisar datos que el usuario haya introducido el.
"""
import logging
import re

_logger = logging.getLogger(__name__)

STAGE_DATE_RE = re.compile(r'(\d{2})/(\d{2})/(\d{4})')


def migrate(cr, version):
    if not version:
        return

    env = _get_env(cr)
    Project = env['project.project']
    Stage = env['project.task.type']

    projects = Project.with_context(active_test=False).search([
        '|', ('date_start', '=', False), ('date', '=', False),
    ])
    _logger.info("[alf_proyecto_alventus] Backfill de fechas: %d proyectos a revisar", len(projects))

    updated = 0
    for project in projects:
        stages = Stage.search([('project_ids', 'in', project.id)])
        if not stages:
            continue

        dated_stages = []
        for stage in stages:
            match = STAGE_DATE_RE.search(stage.name or '')
            if not match:
                continue
            day, month, year = match.groups()
            try:
                stage_date = f"{year}-{month}-{day}"
            except Exception:
                continue
            dated_stages.append((stage.sequence, stage_date))

        if not dated_stages:
            continue

        # Fecha de fin: la mas tardia de todas las etapas con fecha.
        end_date = max(d for _seq, d in dated_stages)

        # Fecha de inicio: la mas temprana EXCLUYENDO la etapa "Dia 0"
        # (sequence == 0), si la hay; si todas son sequence 0 (raro), se usa
        # igualmente la mas temprana disponible.
        non_day0 = [d for seq, d in dated_stages if seq != 0]
        start_date = min(non_day0) if non_day0 else min(d for _seq, d in dated_stages)

        vals = {}
        if not project.date_start:
            vals['date_start'] = start_date
        if not project.date:
            vals['date'] = end_date

        if vals:
            project.write(vals)
            updated += 1

    _logger.info("[alf_proyecto_alventus] Backfill de fechas: %d proyectos actualizados", updated)


def _get_env(cr):
    from odoo import api, SUPERUSER_ID
    return api.Environment(cr, SUPERUSER_ID, {})
