# -*- coding: utf-8 -*-
import base64
import io
import zipfile
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ProjectPhoto(models.Model):
    _name = 'project.photo'
    _description = 'Foto del Grupo/Viaje'
    _order = 'sequence, create_date desc, id'

    project_id = fields.Many2one(
        'project.project',
        string='Viaje',
        required=True,
        ondelete='cascade'
    )
    image = fields.Binary(string='Foto', required=True, attachment=True)
    name = fields.Char(string='Nombre', compute='_compute_name', store=True, readonly=False)
    description = fields.Text(string='Descripción / Comentario')
    sequence = fields.Integer(string='Secuencia', default=10)

    @api.depends('image')
    def _compute_name(self):
        for photo in self:
            if photo.image and not photo.name:
                photo.name = f"Foto {datetime.now().strftime('%d-%m-%Y %H:%M')}"

    def action_download_photo(self):
        """
        Descarga una foto individual.
        Se llama desde el botón del kanban.
        """
        self.ensure_one()
        if not self.image:
            raise UserError(_("Esta foto no tiene datos para descargar."))
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/project.photo/{self.id}/image/{self.name or "foto"}?download=true',
            'target': 'self',
        }

    def action_download_selected_photos(self):
        """
        Descarga las fotos seleccionadas como un archivo ZIP.
        Se llama desde un server action.
        """
        if not self:
            raise UserError(_("No hay fotos seleccionadas para descargar."))
        
        return self._create_zip_and_download(self, f"Fotos_seleccionadas_{datetime.now().strftime('%Y%m%d_%H%M%S')}")

    def _create_zip_and_download(self, photos, zip_name):
        """
        Método auxiliar que crea un ZIP con las fotos dadas y devuelve una acción de descarga.
        """
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for photo in photos:
                if photo.image:
                    # Decodificar la imagen binaria
                    image_data = base64.b64decode(photo.image)
                    # Nombre del archivo dentro del ZIP
                    file_name = photo.name or f"foto_{photo.id}.jpg"
                    # Asegurar que tenga extensión
                    if '.' not in file_name:
                        file_name += '.jpg'
                    zip_file.writestr(file_name, image_data)
        
        buffer.seek(0)
        zip_data = base64.b64encode(buffer.read())
        
        # Crear un attachment temporal con el ZIP
        attachment = self.env['ir.attachment'].create({
            'name': f'{zip_name}.zip',
            'type': 'binary',
            'datas': zip_data,
            'res_model': self._name,
            'mimetype': 'application/zip',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }