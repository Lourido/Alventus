# -*- coding: utf-8 -*-
from odoo import models, fields


class ProjectTask(models.Model):
    _inherit = 'project.task'

    fecha_desde = fields.Datetime(string='Desde')
    fecha_hasta = fields.Datetime(string='Hasta')

    # Aviso en el teléfono para las tareas con hora de inicio (fecha_desde):
    # cuánto antes de esa hora llega. Ver models/push_notification.py.
    aviso_antelacion = fields.Selection(
        [
            ('0', 'A la hora de inicio'),
            ('15', '15 minutos antes'),
            ('30', '30 minutos antes'),
            ('60', '1 hora antes'),
        ],
        string='Aviso en el teléfono',
        default='0',
        help='Si la tarea tiene hora de inicio, cuándo llega el aviso a los '
             'teléfonos que tienen activados los avisos.',
    )

    def copy(self, default=None):
        """
        Al duplicar una tarea (o varias a la vez), también se copian 
        todos sus archivos adjuntos.
        """
        if default is None:
            default = {}
        
        new_tasks = self.env['project.task']
        
        # Iteramos sobre cada tarea por si se copian varias a la vez (ej. al duplicar proyecto)
        for task in self:
            # 1. Duplicar la tarea individualmente
            new_task = super(ProjectTask, task).copy(default)
            
            # 2. Buscar todos los archivos adjuntos de la tarea original
            attachments = self.env['ir.attachment'].search([
                ('res_model', '=', 'project.task'),
                ('res_id', '=', task.id),
            ])
            
            # 3. Copiar cada archivo adjunto a la nueva tarea
            for att in attachments:
                att.copy({
                    'res_id': new_task.id,
                })
            
            # Añadir la nueva tarea al recordset de retorno
            new_tasks |= new_task
            
        return new_tasks