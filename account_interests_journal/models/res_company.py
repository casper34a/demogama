from odoo import models, fields


class ResCompany(models.Model):

    _inherit = 'res.company'

    jorunal_interes_id = fields.Many2one(
        'account.journal',
        'Diario imputacion Intereses',
    )
