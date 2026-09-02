# -*- coding: utf-8 -*-
from odoo import models, fields


class ProjectRouteFile(models.Model):
    _name = 'project.route.file'
    _description = 'Archivo de Ruta del Proyecto'
    _order = 'sequence, id'

    project_id = fields.Many2one(
        'project.project',
        string='Proyecto',
        required=True,
        ondelete='cascade'
    )
    file_data = fields.Binary(string='Archivo', required=True, attachment=True)
    file_name = fields.Char(string='Nombre del archivo')
    description = fields.Text(string='Descripción / Notas')
    sequence = fields.Integer(string='Secuencia', default=10)