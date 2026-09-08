# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class ProjectTaskType(models.Model):
    _inherit = 'project.task.type'

    attachment_ids = fields.One2many(
        'ir.attachment',
        compute='_compute_attachment_ids',
        string='Archivos adjuntos'
    )
    attachment_count = fields.Integer(
        compute='_compute_attachment_ids',
        string='Nº Adjuntos'
    )
    has_attachments = fields.Boolean(
        compute='_compute_attachment_ids',
        string='Tiene adjuntos'
    )

    @api.depends_context('uid')
    def _compute_attachment_ids(self):
        """
        Devuelve los ir.attachment vinculados a esta etapa
        (res_model='project.task.type' y res_id=stage.id).
        """
        Attachment = self.env['ir.attachment']
        for stage in self:
            if stage.id:
                attachments = Attachment.search([
                    ('res_model', '=', 'project.task.type'),
                    ('res_id', '=', stage.id),
                ])
                stage.attachment_ids = attachments
                stage.attachment_count = len(attachments)
                stage.has_attachments = bool(attachments)
            else:
                stage.attachment_ids = Attachment
                stage.attachment_count = 0
                stage.has_attachments = False

    def action_open_attachments(self):
        """Abre la lista completa de adjuntos de esta etapa."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Adjuntos de %s') % self.name,
            'res_model': 'ir.attachment',
            'view_mode': 'list,form',
            'domain': [
                ('res_model', '=', 'project.task.type'),
                ('res_id', '=', self.id),
            ],
            'context': {
                'default_res_model': 'project.task.type',
                'default_res_id': self.id,
                'create': False,  # Solo lectura desde esta vista
            },
            'target': 'current',
        }

    def action_add_attachment(self):
        """Abre el formulario estándar de ir.attachment para subir uno nuevo."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Subir archivo a %s') % self.name,
            'res_model': 'ir.attachment',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': 'project.task.type',
                'default_res_id': self.id,
                'form_view_ref': 'alf_proyecto_alventus.view_attachment_stage_form',
            },
        }
        
    def action_open_stage_form(self):
        """Abre el formulario de esta etapa usando NUESTRA vista con archivos."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': self.name,
            'res_model': 'project.task.type',
            'res_id': self.id,
            'view_mode': 'form',
            'views': [(self.env.ref('alf_proyecto_alventus.view_project_task_type_form_alf').id, 'form')],
            'target': 'current',
        }