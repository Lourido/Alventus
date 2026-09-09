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
        self.ensure_one()
        
        # 1. Crear el proyecto (viaje)
        project = self.env['project.project'].create({
            'name': self.name,
            'user_id': self.env.uid,
            'start_date': self.start_date,
            'date_start': self.start_date,
            'date': self.start_date + timedelta(days=self.num_days - 1),
        })
        
        # 2. Crear la etapa "Día 0 - Antes de salir"
        stage_antes_salir = self.env['project.task.type'].create({
            'name': 'Día 0 - Antes de salir',
            'project_ids': [(4, project.id)],
            'sequence': 0,
        })
        
        # 3. CREAR LAS TAREAS PREDEFINIDAS EN LA ETAPA "Día 0 - Antes de salir"
        default_tasks = [
            "Pagar allí",
            "Visitas programadas/alternativas",
            "Rutas alternativas",
            "Guías locales",
            "Avisos generales",
            "Restaurantes/Bares/Zonas",
            "Precauciones próximo viaje",
            "A mejorar"
        ]
        
        # Preparar y crear las tareas en lote para el nuevo proyecto
        tasks_to_create = [{
            'name': task_name,
            'project_id': project.id,
            'stage_id': stage_antes_salir.id,
        } for task_name in default_tasks]
        
        self.env['project.task'].create(tasks_to_create)
        
        # 4. Crear una etapa por cada día del viaje
        for day in range(1, self.num_days + 1):
            stage_date = self.start_date + timedelta(days=day - 1)
            self.env['project.task.type'].create({
                'name': f'Día {day} - {stage_date.strftime("%d/%m/%Y")}',
                'project_ids': [(4, project.id)],
                'sequence': day,
            })
            
        # 4b. Crear una tarea "Para mañana" en cada etapa del viaje nuevo
        project._create_para_manana_tasks()
            
        # 5. Devolver la acción para abrir el proyecto recién creado
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'form',
            'target': 'current',
        }