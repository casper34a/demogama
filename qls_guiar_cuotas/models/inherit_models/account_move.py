# -*- coding: utf-8 -*-

from odoo import models, fields, api
from datetime import datetime
import time
import logging
_logger = logging.getLogger(__name__)


class AccountMoveLineQLS(models.Model):
    _inherit = "account.move.line"

    indice_id = fields.Many2one('qls.indice.periodo', string="Indice")

    def write(self,vals):

        indice = self.env['qls.indice.periodo'].search([('id','=',vals.get('indice_id'))]) if vals.get('indice_id') else self.indice_id

        if vals.get('name') and indice:
            vals['name'] = ('Deuda por indice: %s %s/%s') % (indice.indice_id.name,
                                                                      indice.mes,
                                                                      indice.anio)
        return super(AccountMoveLineQLS,self).write(vals)


class AccountMoveQLS(models.Model):
    _inherit = "account.move"

    from_coeficiente           = fields.Boolean(default=False)
    quote                      = fields.Integer(string="Cuota", readonly=1, default=0)
    from_interest              = fields.Boolean(default=False)