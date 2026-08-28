# -*- coding: utf-8 -*-
from odoo import models, fields

class ProjectTask(models.Model):
    _inherit = 'project.task'

    fecha_desde = fields.Datetime(string='Fecha desde')
    fecha_hasta = fields.Datetime(string='Fecha hasta')