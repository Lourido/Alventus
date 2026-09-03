# -*- coding: utf-8 -*-
from odoo import models, fields, api
from datetime import timedelta


class ProjectCreateWithTasksWizard(models.TransientModel):
    _name = 'project.create.with.tasks.wizard'
    _description = 'Asistente para crear viaje con etapas por días'

    name = fields.Char(string='Nombre del viaje', required=True)
    start_date = fields.Date(string='Fecha de inicio', required=True, default=fields.Date.today)
    num_days = fields.Integer(string='Número de días', required=True, default=1)

    def action_create(self):
        """
        Crea un nuevo proyecto (viaje) con:
        - Una etapa "Día 0 - Antes de salir" con fecha 7 días antes del inicio
        - Una etapa por cada día del viaje empezando desde la fecha de inicio
        """
        self.ensure_one()

        # 1. Crear el proyecto (viaje)
        # date_start / date son los campos estandar de Odoo (se muestran solos en
        # el Kanban y en la lista de proyectos): "etapa 1" = fecha de inicio,
        # "ultima etapa" = fecha de inicio + (numero de dias - 1).
        project = self.env['project.project'].create({
            'name': self.name,
            'user_id': self.env.uid,
            'start_date': self.start_date,
            'date_start': self.start_date,
            'date': self.start_date + timedelta(days=self.num_days - 1),
        })

        # 2. Crear la etapa "Día 0 - Antes de salir" (una semana antes del inicio)
        day0_date = self.start_date - timedelta(days=7)
        self.env['project.task.type'].create({
            'name': 'Día 0 - Antes de salir',
            'project_ids': [(4, project.id)],
            'sequence': 0,
        })

        # 3. Crear una etapa por cada día del viaje
        for day in range(1, self.num_days + 1):
            stage_date = self.start_date + timedelta(days=day - 1)
            self.env['project.task.type'].create({
                'name': f'Día {day} - {stage_date.strftime("%d/%m/%Y")}',
                'project_ids': [(4, project.id)],
                'sequence': day,
            })

        # 4. Devolver la acción para abrir el proyecto recién creado
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'form',
            'target': 'current',
        }