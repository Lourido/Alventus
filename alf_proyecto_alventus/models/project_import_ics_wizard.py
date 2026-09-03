# -*- coding: utf-8 -*-
import base64
from datetime import datetime, time
from collections import defaultdict
from odoo import models, fields, _
from odoo.exceptions import UserError

class ProjectImportIcsWizard(models.TransientModel):
    _name = 'project.import.ics.wizard'
    _description = 'Importar proyecto desde ICS'

    ics_file = fields.Binary(string='Archivo ICS', required=True)
    ics_filename = fields.Char(string='Nombre del archivo')

    def action_import(self):
        self.ensure_one()
        if not self.ics_file:
            raise UserError(_("Debes seleccionar un archivo ICS."))

        content = base64.b64decode(self.ics_file).decode('utf-8', errors='ignore')
        cal_name, events = self._parse_ics(content)
        if not events:
            raise UserError(_("No se encontraron tareas en el archivo ICS."))

        project = self.env['project.project'].create({'name': cal_name or _('Viaje importado')})

        stages = self.env['project.task.type'].search([('project_ids', 'in', project.id)])
        if stages:
            stages.write({'project_ids': [(3, project.id) for _ in stages]})

        self.env['project.task'].search([('project_id', '=', project.id)]).unlink()

        events_by_day = defaultdict(list)
        for ev in events:
            dt_start = self._parse_ics_datetime(ev.get('DTSTART'))
            day_key = dt_start.date() if dt_start else fields.Date.today()
            events_by_day[day_key].append(ev)

        # "etapa 1" = primer dia con eventos, "ultima etapa" = el ultimo. Se
        # guardan en los campos estandar date_start/date (se ven solos en el
        # Kanban y en la lista de proyectos).
        if events_by_day:
            project.write({
                'date_start': min(events_by_day.keys()),
                'date': max(events_by_day.keys()),
            })

        Stage = self.env['project.task.type']
        Task = self.env['project.task']
        day_counter = 1
        
        for day_date in sorted(events_by_day.keys()):
            day_events = events_by_day[day_date]
            stage_name = 'Día %d - %s' % (day_counter, day_date.strftime('%d/%m/%Y'))
            
            # Calcular inicio y fin del día para esta etapa
            day_start_dt = min((self._parse_ics_datetime(ev.get('DTSTART')) for ev in day_events if self._parse_ics_datetime(ev.get('DTSTART'))), default=datetime.combine(day_date, time.min))
            day_end_dt = max((self._parse_ics_datetime(ev.get('DTEND')) for ev in day_events if self._parse_ics_datetime(ev.get('DTEND'))), default=datetime.combine(day_date, time.max))
            
            new_stage = Stage.create({
                'name': stage_name,
                'project_ids': [(4, project.id)],
                'sequence': day_counter * 10
            })
            
            for ev in day_events:
                ev_start = self._parse_ics_datetime(ev.get('DTSTART')) or day_start_dt
                ev_end = self._parse_ics_datetime(ev.get('DTEND')) or day_end_dt
                
                Task.create({
                    'name': self._ics_unescape(ev.get('SUMMARY', _('Sin título'))),
                    'project_id': project.id,
                    'stage_id': new_stage.id,
                    'parent_id': False,
                    'description': self._ics_unescape(ev.get('DESCRIPTION', '')),
                    'fecha_desde': ev_start,
                    'fecha_hasta': ev_end,
                })
            day_counter += 1

        return {
            'type': 'ir.actions.act_window',
            'name': project.name,
            'res_model': 'project.project',
            'res_id': project.id,
            'view_mode': 'kanban,form',
            'target': 'current',
        }

    def _parse_ics(self, content):
        lines = content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        unfolded = []
        for line in lines:
            if line and line[0] in (' ', '\t') and unfolded:
                unfolded[-1] += line[1:]
            else:
                unfolded.append(line)
        events, current_event, cal_name = [], None, _('Viaje importado')
        for line in unfolded:
            line = line.strip()
            if not line: continue
            if line.startswith('X-WR-CALNAME:'): cal_name = self._ics_unescape(line.split(':', 1)[1])
            elif line == 'BEGIN:VEVENT': current_event = {}
            elif line == 'END:VEVENT': 
                if current_event: events.append(current_event)
                current_event = None
            elif current_event is not None and ':' in line:
                key, value = line.split(':', 1)
                key_base = key.split(';')[0]
                current_event[key_base] = current_event.get(key_base, '') + value
        return cal_name, events

    def _parse_ics_datetime(self, value):
        if not value: return None
        value = value.strip().rstrip('Z')
        try:
            fmt = '%Y%m%dT%H%M%S' if 'T' in value else '%Y%m%d'
            return datetime.strptime(value, fmt)
        except ValueError:
            return None

    def _ics_unescape(self, text):
        if not text: return ''
        return str(text).replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")