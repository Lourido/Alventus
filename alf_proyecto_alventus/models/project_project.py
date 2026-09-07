# -*- coding: utf-8 -*-
import base64
import re
from datetime import datetime, timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectProject(models.Model):
    _inherit = 'project.project'

    start_date = fields.Date(string='Fecha de inicio del viaje')
    end_date = fields.Date(string='Fecha de fin del viaje', compute='_compute_end_date', store=True)
    
    # 1. Campo para contactos de referencia
    reference_contact_ids = fields.Many2many(
        'res.partner',
        'project_reference_contact_rel',
        'project_id',
        'partner_id',
        string='Contactos de Referencia',
        help="Personas o empresas de contacto para este proyecto."
    )

    # 2. Campo para archivos de ruta específicos (KMZ, GPX, GeoJSON)
    route_file_ids = fields.One2many(
        'project.route.file',
        'project_id',
        string='Archivos de Ruta'
    )

    # 3. Campo para fotos del grupo/viaje (NO se copia al duplicar)
    photo_ids = fields.One2many(
        'project.photo',
        'project_id',
        string='Fotos del grupo/viaje'
    )

    @api.depends('task_ids.fecha_hasta')
    def _compute_end_date(self):
        """Calcula la fecha de fin del proyecto como la fecha_hasta más tardía de sus tareas."""
        for project in self:
            tasks_with_end = project.task_ids.filtered(lambda t: t.fecha_hasta)
            if tasks_with_end:
                project.end_date = max(tasks_with_end.mapped('fecha_hasta')).date()
            else:
                project.end_date = False

    @api.model_create_multi
    def create(self, vals_list):
        """
        Al crear un nuevo proyecto, crea automáticamente las tareas 
        predefinidas en la etapa 'Antes de salir'.
        """
        # 1. Crear el proyecto normalmente
        projects = super().create(vals_list)
        
        # 2. Para cada proyecto creado, añadir las tareas por defecto
        for project in projects:
            # Buscar la etapa "Antes de salir"
            stage = self.env['project.task.type'].search([
                ('name', '=', 'Antes de salir')
            ], limit=1)
            
            if stage:
                # Lista de tareas a crear
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
                
                # Preparar los valores para creación en lote (más rápido)
                tasks_to_create = []
                for task_name in default_tasks:
                    tasks_to_create.append({
                        'name': task_name,
                        'project_id': project.id,
                        'stage_id': stage.id,
                    })
                
                # Crear todas las tareas de una vez
                if tasks_to_create:
                    self.env['project.task'].create(tasks_to_create)
            else:
                # Opcional: Registrar en el log si no se encuentra la etapa
                self.env['ir.logging'].create({
                    'name': 'project.project',
                    'type': 'server',
                    'dbname': self.env.cr.dbname,
                    'level': 'WARNING',
                    'message': f"No se encontró la etapa 'Antes de salir' para crear tareas por defecto en el proyecto {project.name}.",
                    'path': 'models/project_project.py',
                    'func': 'create',
                    'line': 70,
                })
        
        return projects

    def copy(self, default=None):
        """
        Al duplicar un proyecto, también se copian los contactos de referencia 
        y los archivos de ruta con sus descripciones.
        """
        self.ensure_one()
        
        # A. Duplicar el proyecto (comportamiento estándar de Odoo)
        new_project = super().copy(default)
        
        # B. Copiar los contactos de referencia al nuevo proyecto
        if self.reference_contact_ids:
            new_project.write({
                'reference_contact_ids': [(6, 0, self.reference_contact_ids.ids)]
            })
        
        # C. Copiar los archivos de ruta con sus descripciones
        for route_file in self.route_file_ids:
            route_file.copy({
                'project_id': new_project.id,
                'file_data': route_file.file_data,
                'file_name': route_file.file_name,
                'description': route_file.description,
            })
        
        return new_project

    def action_export_tasks_to_ics(self):
        """
        Método existente para exportar las tareas a formato ICS.
        """
        self.ensure_one()
        # ---------------------------------------------------------------------
        # PEGA AQUÍ TU LÓGICA EXISTENTE DE EXPORTACIÓN A ICS
        # ---------------------------------------------------------------------
        raise UserError(_("Funcionalidad de exportación ICS pendiente de restaurar en este método."))

    def action_download_all_photos(self):
        """
        Descarga todas las fotos del viaje como un archivo ZIP.
        """
        self.ensure_one()
        if not self.photo_ids:
            raise UserError(_("Este viaje no tiene fotos para descargar."))
        
        zip_name = f"Fotos_{self.name.replace(' ', '_')}_{fields.Date.today().strftime('%Y%m%d')}"
        return self.photo_ids._create_zip_and_download(self.photo_ids, zip_name)

    def action_open_photos_to_download(self):
        """
        Abre la vista de fotos del proyecto para permitir seleccionar 
        y descargar varias fotos usando la acción de servidor.
        """
        self.ensure_one()
        return {
            'name': _('Seleccionar fotos para descargar'),
            'type': 'ir.actions.act_window',
            'res_model': 'project.photo',
            'view_mode': 'list,kanban',
            'domain': [('project_id', '=', self.id)],
            'context': {'default_project_id': self.id},
            'target': 'current',
        }