# -*- coding: utf-8 -*-
from datetime import timedelta, datetime, time
from odoo import models, fields, _
from odoo.exceptions import UserError

class ProjectCreateWithTasksWizard(models.TransientModel):
    _name = 'project.create.with.tasks.wizard'
    _description = 'Crear viaje con etapas por días'

    name = fields.Char(string='Nombre del viaje', required=True)
    start_date = fields.Date(string='Fecha de inicio', required=True, default=fields.Date.today)
    num_days = fields.Integer(string='Número de días', required=True, default=5)

    def action_create(self):
        self.ensure_one()
        if self.num_days < 1:
            raise UserError(_("El número de días debe ser al menos 1."))

        # Calcular fecha final del viaje
        end_date = self.start_date + timedelta(days=self.num_days - 1)
        
        # Formatear fechas en formato dd-mm-yy
        start_str = self.start_date.strftime('%d-%m-%y')
        end_str = end_date.strftime('%d-%m-%y')
        
        # Construir el nombre completo del viaje
        full_name = '%s - del %s al %s' % (self.name, start_str, end_str)

        # Crear el proyecto
        project = self.env['project.project'].create({'name': full_name})

        # Eliminar etapas por defecto
        stages = self.env['project.task.type'].search([('project_ids', 'in', project.id)])
        if stages:
            stages.write({'project_ids': [(3, project.id) for _ in stages]})

        # Eliminar tareas basura
        self.env['project.task'].search([('project_id', '=', project.id)]).unlink()

        Task = self.env['project.task']
        Stage = self.env['project.task.type']
        current_date = self.start_date

        for i in range(1, self.num_days + 1):
            day_str = current_date.strftime('%d-%m-%y')
            stage_name = 'Día %d - %s' % (i, day_str)
            
            dt_desde = datetime.combine(current_date, time.min)
            dt_hasta = datetime.combine(current_date, time.max)

            # Crear la ETAPA (Columna)
            new_stage = Stage.create({
                'name': stage_name,
                'project_ids': [(4, project.id)],
                'sequence': i * 10
            })

            # 👇 CAMBIO: La tarea se llama igual que la etapa
            Task.create({
                'name': stage_name,  # Mismo nombre que la etapa
                'project_id': project.id,
                'stage_id': new_stage.id,
                'parent_id': False,
                'fecha_desde': dt_desde,
                'fecha_hasta': dt_hasta,
            })
            
            current_date += timedelta(days=1)

        return {
            'type': 'ir.actions.act_window',
            'name': project.name,
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'kanban,form',
            'target': 'current',
        }