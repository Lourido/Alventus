# -*- coding: utf-8 -*-
import base64
import re
from datetime import datetime, timedelta

from odoo import models, fields, _
from odoo.exceptions import UserError

class ProjectProject(models.Model):
    _inherit = 'project.project'

    def action_export_tasks_to_ics(self):
        self.ensure_one()
        tasks = self.task_ids.filtered(lambda t: not t.parent_id)
        if not tasks:
            raise UserError(_("No hay tareas en este proyecto para exportar."))

        ics_content = self._generate_ics_content(tasks)
        project_name = self.name or 'Proyecto'
        safe_name = "".join(c for c in project_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        filename = f"{safe_name}_tareas.ics"

        attachment = self.env['ir.attachment'].create({
            'name': filename,
            'type': 'binary',
            'datas': base64.b64encode(ics_content.encode('utf-8')),
            'res_model': self._name,
            'res_id': self.id,
            'mimetype': 'text/calendar',
        })

        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }

    def _generate_ics_content(self, tasks):
        lines = [
            "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Odoo//ALF Viajes//ES",
            "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
            "X-WR-CALNAME:%s" % self._ics_escape(self.name or 'Proyecto'),
            "X-WR-TIMEZONE:Europe/Madrid",
        ]
        for task in tasks:
            all_tasks = task | task.child_ids
            for t in all_tasks:
                lines.extend(self._task_to_vevent(t))
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    def _task_to_vevent(self, task):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', 'odoo')
        lines = ["BEGIN:VEVENT", "UID:%s-task-%s@odoo" % (base_url, task.id)]
        lines.append("DTSTAMP:%s" % self._format_datetime(fields.Datetime.now()))
        lines.append("SUMMARY:%s" % self._ics_escape(task.name or _('Sin título')))

        # USAR LOS NUEVOS CAMPOS
        dt_start = fields.Datetime.from_string(task.fecha_desde) if task.fecha_desde else None
        dt_end = fields.Datetime.from_string(task.fecha_hasta) if task.fecha_hasta else None

        if dt_start and dt_end:
            lines.append("DTSTART:%s" % self._format_datetime(dt_start))
            lines.append("DTEND:%s" % self._format_datetime(dt_end))
        elif dt_start:
            lines.append("DTSTART:%s" % self._format_datetime(dt_start))
            lines.append("DTEND:%s" % self._format_datetime(dt_start + timedelta(hours=1)))
        elif dt_end:
            lines.append("DTSTART:%s" % self._format_datetime(dt_end))
            lines.append("DTEND:%s" % self._format_datetime(dt_end))
        else:
            today = fields.Date.today()
            lines.append("DTSTART;VALUE=DATE:%s" % self._format_date_only(today))
            lines.append("DTEND;VALUE=DATE:%s" % self._format_date_only(today + timedelta(days=1)))

        desc = self._strip_html(task.description) if task.description else ""
        attachments = self.env['ir.attachment'].search([('res_model', '=', 'project.task'), ('res_id', '=', task.id)])
        if attachments:
            if desc: desc += "\n\n"
            desc += "--- Archivos adjuntos ---\n"
            for att in attachments:
                desc += f"- {att.name}: {base_url}/web/content/{att.id}/{att.name}?download=true\n"
        if desc:
            lines.append("DESCRIPTION:%s" % self._ics_escape(desc.strip()))

        if self.name: lines.append("CATEGORIES:%s" % self._ics_escape(self.name))
        if task.stage_id: lines.append("STATUS:%s" % self._ics_escape(task.stage_id.name))
        if task.write_date: lines.append("LAST-MODIFIED:%s" % self._format_datetime(fields.Datetime.from_string(task.write_date)))
        lines.append("END:VEVENT")
        return lines

    def _format_datetime(self, dt):
        if isinstance(dt, fields.Date): dt = datetime(dt.year, dt.month, dt.day)
        return dt.strftime("%Y%m%dT%H%M%SZ")

    def _format_date_only(self, dt):
        return dt.strftime("%Y%m%d")

    def _ics_escape(self, text):
        if not text: return ''
        text = str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
        return text

    def _strip_html(self, text):
        if not text: return ''
        clean = re.sub(r'<[^>]+>', ' ', text)
        return re.sub(r'\s+', ' ', clean).strip()