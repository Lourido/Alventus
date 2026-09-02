# -*- coding: utf-8 -*-
import logging
import time
import re
from datetime import timedelta, date

from odoo import models, fields, api

_logger = logging.getLogger(__name__)


class ProjectDuplicateWizard(models.TransientModel):
    _name = 'project.duplicate.wizard'
    _description = 'Asistente para duplicar viaje con nueva fecha'

    project_id = fields.Many2one('project.project', string='Proyecto original', readonly=True)
    new_start_date = fields.Date(string='Nueva fecha de inicio', required=True, default=fields.Date.today)
    new_name = fields.Char(string='Nuevo nombre del viaje', required=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            project = self.env['project.project'].browse(active_id)
            res['project_id'] = project.id
            res['new_name'] = f"{project.name} (copia)"
            if project.start_date:
                res['new_start_date'] = project.start_date
        return res

    def action_duplicate(self):
        self.ensure_one()
        original = self.project_id
        total_start = time.time()
        
        # 1. Calcular delta_days
        base_date = original.start_date
        if not base_date:
            first_task = self.env['project.task'].search([
                ('project_id', '=', original.id),
                ('fecha_desde', '!=', False)
            ], order='fecha_desde asc', limit=1)
            base_date = first_task.fecha_desde.date() if first_task and first_task.fecha_desde else self.new_start_date
        delta_days = (self.new_start_date - base_date).days
        _logger.info("[PERF] Paso 1 (Calc delta): %.4fs", time.time() - total_start)

        # 2. Crear el proyecto nuevo desde cero
        step2_start = time.time()
        new_project = self.env['project.project'].with_context(
            tracking_disable=True,
            mail_create_nosubscribe=True,
            mail_create_nolog=True,
            mail_notify_force_send=False,
        ).create({
            'name': self.new_name,
            'user_id': original.user_id.id if original.user_id else self.env.uid,
            'start_date': self.new_start_date,
            'description': original.description,
            'privacy_visibility': original.privacy_visibility,
            'allow_task_dependencies': original.allow_task_dependencies,
            'label_tasks': original.label_tasks,
            # Copiar los contactos de referencia al nuevo proyecto
            'reference_contact_ids': [(6, 0, original.reference_contact_ids.ids)],
        })
        
        # Copiar adjuntos a nivel de PROYECTO (si los tiene)
        project_attachments = self.env['ir.attachment'].search([
            ('res_model', '=', 'project.project'),
            ('res_id', '=', original.id),
        ])
        for att in project_attachments:
            att.copy({'res_id': new_project.id})
            
        _logger.info("[PERF] Paso 2 (Crear Proyecto y copiar adjuntos/contactos): %.4fs", time.time() - step2_start)

        # 3. Crear las nuevas etapas con fechas ajustadas
        step3_start = time.time()
        original_stages = self.env['project.task.type'].search([
            ('project_ids', 'in', original.id),
        ], order='sequence asc, id asc')

        stage_mapping = {}
        for old_stage in original_stages:
            new_stage_name = self._adjust_stage_name(old_stage.name, delta_days)
            new_stage = self.env['project.task.type'].with_context(tracking_disable=True).create({
                'name': new_stage_name,
                'project_ids': [(4, new_project.id)],
                'sequence': old_stage.sequence,
            })
            stage_mapping[old_stage.id] = new_stage
        _logger.info("[PERF] Paso 3 (Crear Etapas): %.4fs", time.time() - step3_start)

        # 4. Leer datos de tareas (OPTIMIZACIÓN CLAVE: 1 sola consulta SQL)
        step4_start = time.time()
        original_tasks_data = self.env['project.task'].search_read(
            [('project_id', '=', original.id)],
            ['id', 'name', 'description', 'sequence', 'stage_id', 'fecha_desde', 'fecha_hasta', 'user_ids'],
            order='sequence asc, id asc'
        )
        _logger.info("[PERF] Paso 4 (Leer Tareas): %.4fs", time.time() - step4_start)

        if not original_tasks_data:
            return self._open_project(new_project)

        # 5. Preparar datos en memoria (SIN user_ids para evitar triggers de email)
        step5_start = time.time()
        task_vals_list = []
        old_to_new_task_map = []
        
        for task_data in original_tasks_data:
            old_stage_id = task_data['stage_id'][0] if task_data['stage_id'] else False
            new_stage = stage_mapping.get(old_stage_id)
            
            fecha_desde = task_data['fecha_desde']
            fecha_hasta = task_data['fecha_hasta']
            
            task_vals = {
                'name': task_data['name'],
                'project_id': new_project.id,
                'stage_id': new_stage.id if new_stage else False,
                'description': task_data['description'],
                'fecha_desde': fecha_desde + timedelta(days=delta_days) if fecha_desde else False,
                'fecha_hasta': fecha_hasta + timedelta(days=delta_days) if fecha_hasta else False,
                'sequence': task_data['sequence'],
                'parent_id': False,
            }
            task_vals_list.append(task_vals)
            old_to_new_task_map.append((task_data['id'], task_vals, task_data['user_ids']))
        _logger.info("[PERF] Paso 5 (Preparar memoria): %.4fs", time.time() - step5_start)

        # 6. Crear tareas en BULK (Sin notificaciones)
        step6_start = time.time()
        new_tasks = self.env['project.task'].with_context(
            tracking_disable=True,
            mail_create_nosubscribe=True,
            mail_create_nolog=True,
            mail_notify_force_send=False,
        ).create(task_vals_list)
        _logger.info("[PERF] Paso 6 (CREAR TAREAS BULK): %.4fs", time.time() - step6_start)

        # 7. Asignar usuarios silenciosamente y mapear IDs
        step7_start = time.time()
        old_to_new_task = {}
        for new_task, (old_id, vals, user_ids) in zip(new_tasks, old_to_new_task_map):
            old_to_new_task[old_id] = new_task
            # Asignar usuarios sin disparar notificaciones de correo
            if user_ids:
                new_task.sudo().with_context(
                    tracking_disable=True,
                    mail_create_nolog=True,
                    mail_notify_force_send=False,
                ).write({
                    'user_ids': [(6, 0, user_ids)]
                })
        _logger.info("[PERF] Paso 7 (Asignar usuarios y mapear): %.4fs", time.time() - step7_start)

        # 8. Leer adjuntos en BULK (OPTIMIZACIÓN CLAVE: 1 sola consulta SQL)
        step8_start = time.time()
        attachments_data = self.env['ir.attachment'].search_read(
            [('res_model', '=', 'project.task'), ('res_id', 'in', [t['id'] for t in original_tasks_data])],
            ['id', 'name', 'datas', 'mimetype', 'description', 'res_id']
        )
        _logger.info("[PERF] Paso 8 (Leer Adjuntos): %.4fs", time.time() - step8_start)

        # 9. Crear adjuntos en BULK
        step9_start = time.time()
        if attachments_data:
            att_vals_list = []
            for att_data in attachments_data:
                new_task = old_to_new_task.get(att_data['res_id'])
                if new_task:
                    att_vals_list.append({
                        'name': att_data['name'],
                        'datas': att_data['datas'],
                        'res_model': 'project.task',
                        'res_id': new_task.id,
                        'mimetype': att_data['mimetype'],
                        'description': att_data['description'],
                    })
            
            if att_vals_list:
                self.env['ir.attachment'].with_context(tracking_disable=True).create(att_vals_list)
        _logger.info("[PERF] Paso 9 (CREAR ADJUNTOS BULK): %.4fs", time.time() - step9_start)

        _logger.info("[PERF] TIEMPO TOTAL DE DUPLICACIÓN: %.4fs", time.time() - total_start)
        
                # 10. Copiar archivos de ruta con sus descripciones
        step10_start = time.time()
        for route_file in original.route_file_ids:
            route_file.copy({
                'project_id': new_project.id,
                'file_data': route_file.file_data,
                'file_name': route_file.file_name,
                'description': route_file.description,
            })
        _logger.info("[PERF] Paso 10 (Copiar Archivos de Ruta): %.4fs", time.time() - step10_start)

        return self._open_project(new_project)

    def _open_project(self, project):
        return {
            'type': 'ir.actions.act_window',
            'name': project.name,
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _adjust_stage_name(self, name, delta_days):
        date_pattern = r'(\d{2}/\d{2}/\d{4})'
        match = re.search(date_pattern, name)
        if match:
            date_str = match.group(1)
            day, month, year = map(int, date_str.split('/'))
            try:
                original_date = date(year, month, day)
                new_date = original_date + timedelta(days=delta_days)
                return name.replace(date_str, new_date.strftime('%d/%m/%Y'))
            except ValueError:
                return name
        return name