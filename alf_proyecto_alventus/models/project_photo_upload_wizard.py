# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectPhotoUploadWizard(models.TransientModel):
    _name = 'project.photo.upload.wizard'
    _description = 'Asistente para subir múltiples fotos'

    project_id = fields.Many2one('project.project', string='Viaje', required=True, readonly=True)
    
    # Campo Many2many a ir.attachment (requerido por el widget many2many_binary)
    attachment_ids = fields.Many2many(
        'ir.attachment', 
        string='Fotos',
        help="Selecciona una o varias fotos para subir al viaje"
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        if active_id:
            res['project_id'] = active_id
        return res

    def action_upload_photos(self):
        self.ensure_one()
        
        if not self.attachment_ids:
            raise UserError(_("Por favor, selecciona al menos una foto para subir."))
        
        photos_created = 0
        for attachment in self.attachment_ids:
            if attachment.datas:
                self.env['project.photo'].create({
                    'project_id': self.project_id.id,
                    'image': attachment.datas,
                    'name': attachment.name,
                })
                photos_created += 1
        
        return {
            'type': 'ir.actions.act_window',
            'name': self.project_id.name,
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }